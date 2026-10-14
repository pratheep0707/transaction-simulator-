# Architecture & Transaction Execution Diagrams

This document contains architectural diagrams and execution flow models for the **Transaction Management and Concurrency Control Simulator**.

---

## 1. System Architecture Diagram

```mermaid
graph TD
    subgraph UI_Layer ["Presentation Layer (Streamlit)"]
        UI_Dash["Overview Dashboard"]
        UI_Lifecycle["Lifecycle & ACID Explorer"]
        UI_Scenarios["Concurrency Scenarios Runner"]
        UI_History["History & Audit Logs"]
        UI_Plots["Plotly Visualization Engine"]
    end

    subgraph Coord_Layer ["Concurrency & Coordination Layer"]
        SC["ScenarioCoordinator"]
        EvtLog["EventLogger (Thread-Safe)"]
        Th1["Worker Thread: T1"]
        Th2["Worker Thread: T2"]
    end

    subgraph Engine_Layer ["Transaction Engine (Domain & State)"]
        TM1["ManagedTransaction (T1)"]
        TM2["ManagedTransaction (T2)"]
        SM["State Machine (Active/Partially Committed/Committed/Failed/Aborted)"]
    end

    subgraph Data_Layer ["Data Access & PostgreSQL Driver"]
        Repo["SimulatorRepository"]
        Driver["psycopg 3 (SSL/TLS Enabled)"]
    end

    subgraph DB_Layer ["Database Engine (Supabase PostgreSQL)"]
        PG_MVCC["MVCC Snapshot Engine"]
        PG_LockMgr["Lock Manager (Row Locks / FOR UPDATE)"]
        PG_Deadlock["Deadlock Detector (Wait-For Graph Cycle)"]
        PG_WAL["Write-Ahead Log (WAL)"]
        Table_Data[("sim_test_data")]
        Table_Runs[("sim_runs")]
        Table_Events[("sim_events")]
    end

    UI_Scenarios --> SC
    SC --> Th1
    SC --> Th2
    Th1 --> TM1
    Th2 --> TM2
    TM1 --> SM
    TM2 --> SM
    TM1 --> Driver
    TM2 --> Driver
    Driver --> PG_LockMgr
    Driver --> PG_MVCC
    Driver --> PG_Deadlock
    Driver --> PG_WAL
    PG_WAL --> Table_Data
    Repo --> Driver
    Repo --> Table_Runs
    Repo --> Table_Events
    EvtLog --> Repo
    EvtLog --> UI_Plots
```

---

## 2. Transaction Lifecycle State Transitions

```mermaid
stateDiagram-v2
    [*] --> ACTIVE: BEGIN TRANSACTION
    ACTIVE --> ACTIVE: READ / WRITE / SAVEPOINT
    ACTIVE --> PARTIALLY_COMMITTED: Final Statement Executed
    PARTIALLY_COMMITTED --> COMMITTED: WAL Flush Acknowledged (COMMIT)
    PARTIALLY_COMMITTED --> FAILED: WAL Flush Failure
    ACTIVE --> FAILED: Execution Exception / Deadlock (40P01) / Serialization (40001)
    ACTIVE --> ABORTED: Explicit ROLLBACK
    FAILED --> ABORTED: Transaction Rollback (Undo)
    COMMITTED --> [*]
    ABORTED --> [*]
```

---

## 3. Concurrency Scenario A: Lost Update Anomaly Flow

```mermaid
sequenceDiagram
    autonumber
    actor System as Coordinator
    participant T1 as Transaction T1
    participant DB as PostgreSQL (sim_test_data)
    participant T2 as Transaction T2

    System->>DB: Reset X = 100.0
    T1->>DB: BEGIN TRANSACTION (Read Committed)
    T1->>DB: SELECT value FROM sim_test_data (Reads 100.0)
    Note over T1: T1 computes 100 + 50 = 150 (Held in memory)
    T1->>System: Signal: T1 Read Complete
    System->>T2: Start T2 Execution
    T2->>DB: BEGIN TRANSACTION (Read Committed)
    T2->>DB: SELECT value FROM sim_test_data (Reads 100.0)
    Note over T2: T2 computes 100 - 20 = 80
    T2->>DB: UPDATE sim_test_data SET value = 80.0
    T2->>DB: COMMIT (Value 80.0 becomes durable)
    T2->>System: Signal: T2 Commit Complete
    System->>T1: Resume T1 Execution
    Note over T1: T1 writes using its STALE calculation!
    T1->>DB: UPDATE sim_test_data SET value = 150.0
    T1->>DB: COMMIT (Overwrites T2's update!)
    Note over DB: Final Value in DB = 150.0 (T2's update is LOST! Expected = 130.0)
```

---

## 4. Concurrency Scenario B: Pessimistic Locking Flow (`SELECT ... FOR UPDATE`)

```mermaid
sequenceDiagram
    autonumber
    actor System as Coordinator
    participant T1 as Transaction T1
    participant LockMgr as PostgreSQL Lock Manager
    participant T2 as Transaction T2

    System->>LockMgr: Reset X = 100.0
    T1->>LockMgr: BEGIN
    T1->>LockMgr: SELECT ... FOR UPDATE (Acquires Exclusive Row Lock)
    T1->>System: Signal: T1 Lock Acquired
    System->>T2: Start T2
    T2->>LockMgr: BEGIN
    T2->>LockMgr: SELECT ... FOR UPDATE (Requests Row Lock)
    Note over LockMgr, T2: Lock Conflict! PostgreSQL SUSPENDS T2 worker thread
    Note over T1: T1 computes 100 + 50 = 150
    T1->>LockMgr: UPDATE sim_test_data SET value = 150.0
    T1->>LockMgr: COMMIT
    Note over LockMgr: T1 COMMIT releases exclusive row lock
    Note over LockMgr, T2: PostgreSQL UNBLOCKS T2!
    T2->>LockMgr: Read committed value = 150.0
    Note over T2: T2 computes 150 - 20 = 130
    T2->>LockMgr: UPDATE sim_test_data SET value = 130.0
    T2->>LockMgr: COMMIT
    Note over LockMgr: Final Value in DB = 130.0 (Mathematically Correct)
```

---

## 5. Concurrency Scenario F: Deadlock Wait-For Graph Cycle

```mermaid
graph LR
    subgraph Wait_For_Cycle ["Circular Dependency in Lock Manager"]
        T1["Transaction T1<br>(Holds Lock on Item A)"]
        T2["Transaction T2<br>(Holds Lock on Item B)"]
        ItemA["Item A"]
        ItemB["Item B"]

        T1 -- "Holds Lock" --> ItemA
        T2 -- "Holds Lock" --> ItemB
        T1 -. "Blocked Waiting for" .-> ItemB
        T2 -. "Blocked Waiting for (Deadlock!)" .-> ItemA
    end
```
