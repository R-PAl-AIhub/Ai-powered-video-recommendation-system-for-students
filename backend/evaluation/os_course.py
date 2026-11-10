"""A small labelled course used by the test suite and the offline evaluation.

Two playlists of short operating-systems lectures (the transcripts are original
text written for this project), a syllabus, an exam paper, lecture notes, and the
expected answer for every syllabus topic: which videos are acceptable, or that
the topic is a gap because no video covers it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SENTENCE_SECONDS = 25.0  # each transcript sentence is one caption segment of this length


@dataclass(frozen=True)
class LabelledVideo:
    youtube_id: str
    title: str
    transcript: str  # one sentence per line; "" = the video has no captions
    description: str = ""
    views: int = 50_000
    likes: int = 1_500
    duration_s: int = 0  # 0 = derive from the transcript length

    @property
    def sentences(self) -> list[str]:
        return [line.strip() for line in self.transcript.strip().splitlines() if line.strip()]

    @property
    def seconds(self) -> int:
        return self.duration_s or int(len(self.sentences) * SENTENCE_SECONDS) or 600


@dataclass(frozen=True)
class LabelledPlaylist:
    youtube_id: str
    title: str
    channel: str
    videos: list[LabelledVideo] = field(default_factory=list)


MAIN = LabelledPlaylist(
    youtube_id="PLmainOperatingSystems0001",
    title="Operating Systems Full Course",
    channel="CS Lectures",
    videos=[
        LabelledVideo(
            "osIntro0001",
            "Introduction to Operating Systems",
            """
            Welcome to this course on operating systems.
            An operating system is the software that sits between the user programs and the computer hardware.
            The main concept of an operating system is that it acts as a resource manager for the processor, memory and devices.
            It hides the messy details of the hardware and gives programs a clean and simple interface.
            The core of the operating system is called the kernel and it always stays in main memory.
            The processor runs in two modes, called user mode and kernel mode, to protect the system.
            Ordinary applications run in user mode and cannot touch the hardware directly.
            In the coming lectures we will study processes, memory management and storage one by one.
            """,
            views=900_000,
            likes=21_000,
        ),
        LabelledVideo(
            "osSyscall02",
            "System Calls and Operating System Structure",
            """
            In this lecture we look at system calls and then at the structure of an operating system.
            A system call is the way a user program requests a service from the kernel.
            When a program wants to read a file it makes a read system call and control switches to kernel mode.
            Examples of system calls are open, read, write, fork and exit.
            System calls are usually wrapped by library functions so programmers rarely call them directly.
            The parameters of a system call are passed in registers or on the stack.
            Now let us discuss how the operating system itself is structured.
            In a monolithic kernel all services such as file system and device drivers run together in kernel space.
            A monolithic structure is fast because components call each other directly, but one bug can crash everything.
            In a microkernel only the minimum, such as scheduling and message passing, stays inside the kernel.
            In the microkernel design the file system and drivers run as separate servers in user space.
            A microkernel is more reliable and easier to extend, but message passing makes it slower.
            A layered structure arranges the operating system as layers where each layer uses only the layer below.
            Most modern systems are hybrids that mix the monolithic and microkernel ideas.
            """,
            views=400_000,
            likes=9_000,
        ),
        LabelledVideo(
            "osProcess03",
            "Process Concept, Process States and PCB",
            """
            A process is a program in execution.
            During its life a process moves through several process states.
            The process states are new, ready, running, waiting and terminated.
            A process in the ready state is waiting to be assigned to the processor.
            When it waits for input or output the process moves to the waiting state.
            The operating system keeps all information about a process in a data structure called the process control block.
            The process control block, or PCB, stores the process identifier, the program counter and the register values.
            The PCB also keeps scheduling information, memory limits and the list of open files.
            Switching the processor from one process to another is called a context switch.
            During context switching the state of the old process is saved into its PCB.
            Then the saved state of the new process is loaded from its own PCB.
            Context switching is pure overhead because no useful work is done during the switch.
            """,
            views=650_000,
            likes=15_000,
        ),
        LabelledVideo(
            "osSched0004",
            "CPU Scheduling: FCFS and SJF",
            """
            CPU scheduling decides which ready process gets the processor next.
            We compare scheduling algorithms using waiting time, turnaround time and response time.
            The simplest algorithm is first come first served, written FCFS.
            In FCFS the process that arrives first is served first, like a queue at a ticket counter.
            FCFS is non-preemptive and easy to implement with a simple queue.
            Its problem is the convoy effect, where short processes wait behind one long process.
            The average waiting time under FCFS can therefore be very high.
            The next algorithm is shortest job first, written SJF.
            SJF selects the process with the smallest burst time.
            Shortest job first gives the minimum average waiting time and is provably optimal.
            The difficulty with SJF is that the burst time of a process is not known in advance.
            The preemptive version of SJF is called shortest remaining time first.
            """,
            views=800_000,
            likes=19_000,
        ),
        LabelledVideo(
            "osRoundRob5",
            "Round Robin Scheduling with Time Quantum",
            """
            Round robin is the scheduling algorithm designed for time sharing systems.
            In round robin every process gets a small unit of processor time called the time quantum.
            When the time quantum expires the process is preempted and placed at the back of the ready queue.
            The ready queue is treated as a circular queue.
            If the time quantum is very large, round robin behaves just like first come first served.
            If the time quantum is very small there are too many context switches.
            Round robin gives good response time, which is why interactive systems use it.
            Let us solve a round robin example with a time quantum of two milliseconds.
            """,
            views=700_000,
            likes=16_000,
        ),
        LabelledVideo(
            "osSync00006",
            "Process Synchronization, Critical Section and Semaphores",
            """
            When several processes share data we need process synchronization.
            The part of the program that accesses shared data is called the critical section.
            The critical section problem is to make sure that only one process is inside its critical section at a time.
            A solution to the critical section problem must provide mutual exclusion, progress and bounded waiting.
            If two processes update a shared counter together we get a race condition.
            Peterson's solution is a classic software answer for two processes.
            Now we move on to semaphores, a synchronization tool proposed by Dijkstra.
            A semaphore is an integer variable that is accessed only through two atomic operations, wait and signal.
            The wait operation decrements the semaphore and blocks the process if the value becomes negative.
            The signal operation increments the semaphore and wakes up a waiting process.
            A binary semaphore takes only the values zero and one and is used as a mutex lock.
            A counting semaphore controls access to a resource that has several instances.
            Semaphores solve the producer consumer problem and the readers writers problem.
            Used carelessly, semaphores can lead to deadlock and starvation.
            """,
            views=600_000,
            likes=14_000,
        ),
        LabelledVideo(
            "osDeadlock7",
            "Deadlocks: Necessary Conditions and Deadlock Prevention",
            """
            A deadlock is a situation where a set of processes are blocked forever, each waiting for a resource held by another.
            There are four necessary conditions for deadlock to occur.
            The first necessary condition is mutual exclusion, meaning a resource can be used by only one process at a time.
            The second condition is hold and wait, where a process holds one resource while waiting for another.
            The third condition is no preemption, so a resource cannot be taken away from a process by force.
            The fourth condition is circular wait, where processes form a cycle of waiting.
            All four necessary conditions must hold together for a deadlock to happen.
            We can draw a resource allocation graph to see whether these conditions are present.
            Now let us talk about deadlock prevention.
            Deadlock prevention means making sure that at least one of the four conditions can never hold.
            To prevent hold and wait we force a process to request all of its resources at once.
            To attack no preemption we take resources back when a request cannot be granted.
            To prevent circular wait we number the resources and require processes to request them in increasing order.
            Deadlock prevention is simple but it leads to low resource utilisation.
            Preventing mutual exclusion is usually impossible because some resources cannot be shared.
            In the next lecture we will see deadlock avoidance, which is less restrictive than prevention.
            """,
            views=750_000,
            likes=18_000,
        ),
        LabelledVideo(
            "osBankers08",
            "Banker's Algorithm for Deadlock Avoidance",
            """
            Deadlock avoidance needs advance information about the maximum resources each process may request.
            The system is in a safe state if there is a safe sequence in which every process can finish.
            The banker's algorithm is the standard deadlock avoidance algorithm for multiple instances of resources.
            The banker's algorithm uses four data structures called available, max, allocation and need.
            The need matrix is calculated as max minus allocation.
            When a process makes a request, the banker's algorithm pretends to grant it and runs the safety algorithm.
            If the resulting state is safe the request is granted, otherwise the process must wait.
            Let us work through a banker's algorithm example with five processes and three resource types.
            We find the safe sequence by repeatedly choosing a process whose need is less than or equal to available.
            The name comes from a banker who never lends cash in a way that leaves other customers unsatisfied.
            """,
            views=1_200_000,
            likes=30_000,
        ),
        LabelledVideo(
            "osPaging009",
            "Paging in Memory Management",
            """
            Paging is a memory management scheme that removes the need for contiguous allocation.
            In paging the physical memory is divided into fixed size blocks called frames.
            The logical memory of a process is divided into blocks of the same size called pages.
            A page table maps every page number to the frame number where that page is stored.
            The logical address is split into a page number and a page offset.
            Paging removes external fragmentation but it can cause internal fragmentation in the last page.
            Looking up the page table on every access is slow, so we use a translation lookaside buffer.
            The translation lookaside buffer, or TLB, is a small fast cache of recent page table entries.
            """,
            views=850_000,
            likes=20_000,
        ),
        LabelledVideo(
            "osVirtual10",
            "Virtual Memory, Demand Paging and Page Replacement",
            """
            Virtual memory lets a process run even when it is not completely loaded in main memory.
            With virtual memory a program can be larger than the physical memory of the machine.
            Virtual memory is commonly implemented using demand paging.
            In demand paging a page is brought into memory only when it is actually needed.
            A valid invalid bit in the page table tells us whether the page is currently in memory.
            If the process touches a page that is not in memory, a page fault occurs.
            On a page fault the operating system finds the page on disk and loads it into a free frame.
            Pure demand paging never loads a page until that page is referenced.
            Now suppose a page fault occurs and there is no free frame available.
            Then we need a page replacement algorithm to choose a victim page to remove.
            The FIFO page replacement algorithm replaces the page that has been in memory the longest.
            FIFO page replacement can suffer from Belady's anomaly, where more frames give more page faults.
            The optimal page replacement algorithm replaces the page that will not be used for the longest time.
            The optimal algorithm cannot be implemented because it needs future knowledge.
            The least recently used algorithm, LRU, replaces the page that has not been used for the longest time.
            LRU page replacement is a good practical approximation of the optimal algorithm.
            """,
            views=950_000,
            likes=23_000,
        ),
    ],
)

REVISION = LabelledPlaylist(
    youtube_id="PLrevisionOperatingSys0002",
    title="OS Quick Revision",
    channel="Exam Prep",
    videos=[
        LabelledVideo(
            "rvDeadlock1",
            "Deadlock in One Shot - Quick Revision",
            """
            This is a quick revision of deadlock for your exam.
            Deadlock happens when processes wait for each other forever.
            Remember the four necessary conditions: mutual exclusion, hold and wait, no preemption and circular wait.
            For deadlock avoidance remember the banker's algorithm and the idea of a safe state.
            In the banker's algorithm need equals max minus allocation.
            Deadlock detection uses a wait for graph, and recovery is done by killing a process.
            """,
            views=120_000,
            likes=5_000,
        ),
        LabelledVideo(
            "rvSegment02",
            "Segmentation Explained",
            """
            Segmentation is a memory management technique that matches the way programmers see a program.
            In segmentation a program is divided into variable sized segments such as code, data and stack.
            Each segment has a name and a length.
            The segment table stores a base address and a limit for every segment.
            A logical address in segmentation consists of a segment number and an offset.
            If the offset is greater than the limit, the hardware raises a trap.
            Segmentation suffers from external fragmentation because segments have different sizes.
            Segmentation with paging combines both ideas.
            """,
            views=90_000,
            likes=3_000,
        ),
        LabelledVideo(
            "rvDisk00003",
            "Disk Scheduling Algorithms: FCFS, SSTF, SCAN",
            """
            Disk scheduling decides the order in which pending disk requests are served.
            The goal of disk scheduling is to reduce the seek time, the time to move the disk arm.
            In FCFS disk scheduling the requests are served in the order they arrive.
            Shortest seek time first, SSTF, serves the request closest to the current head position.
            SSTF disk scheduling can cause starvation of far away requests.
            In SCAN the disk arm moves from one end of the disk to the other like an elevator.
            C-SCAN returns to the beginning without serving requests on the way back.
            LOOK and C-LOOK only travel as far as the last request in each direction.
            """,
            views=110_000,
            likes=4_000,
        ),
        LabelledVideo(
            "rvThreads04",
            "Threads and Multithreading",
            """
            A thread is a lightweight process and the basic unit of processor utilisation.
            Threads of the same process share the code section, the data section and open files.
            Each thread has its own program counter, register set and stack.
            The benefits of threads are responsiveness, resource sharing and economy.
            User level threads are managed by a thread library without kernel support.
            Kernel level threads are managed directly by the operating system.
            Multithreading models map user threads to kernel threads as many to one, one to one or many to many.
            Creating a thread is much cheaper than creating a new process.
            """,
            views=130_000,
            likes=4_500,
        ),
        LabelledVideo(
            "rvFiles0005",
            "File Allocation Methods - Contiguous, Linked, Indexed",
            "",
            description=(
                "File allocation methods in operating systems: contiguous allocation, "
                "linked allocation and indexed allocation, with advantages and disadvantages."
            ),
            views=70_000,
            likes=2_000,
            duration_s=540,
        ),
    ],
)

PLAYLISTS = [MAIN, REVISION]

SYLLABUS = """\
Operating Systems
Course Code: CS502    Credits: 3

Unit 1: Introduction
Concept of Operating Systems, System Calls, Structure of an OS - Monolithic, Microkernel.
Unit 2: Processes and Scheduling
Process states, Process Control Block (PCB), Context switching, Threads.
CPU Scheduling: FCFS, SJF, Round Robin.
Unit 3: Synchronization and Deadlocks
Critical section problem, Semaphores, Necessary conditions for deadlock, Deadlock prevention,
Banker's algorithm.
Unit 4: Memory Management
Paging, Segmentation, Virtual memory, Demand paging, Page replacement algorithms.
Unit 5: Storage and Protection
Disk scheduling, File allocation methods, RAID levels, Access control lists,
Public key cryptography.

Text Books:
1. Operating System Concepts, Silberschatz and Galvin
"""

EXAM = """\
Operating Systems - End Semester Examination
Time: 3 hours    Full Marks: 70

1. (a) What is a deadlock? State the four necessary conditions for deadlock. [5]
(b) Explain the banker's algorithm for deadlock avoidance with a suitable example. [10]
2. What is a page fault? Explain demand paging with a neat diagram. [7]
3. Consider five processes with given burst times. Calculate the average waiting time using
FCFS and SJF scheduling. [8]
4. Explain the banker's algorithm safety check and find the safe sequence. [7]
5. Describe the LRU and FIFO page replacement algorithms. [7]
6. What is a semaphore? Solve the producer consumer problem using semaphores. [8]
"""

NOTES = """\
Lecture notes - Unit 3

Deadlock handling
A set of processes is deadlocked when every process in the set waits for a resource held by
another process in the set. The teacher stressed that the banker's algorithm keeps the system in
a safe state by checking the need matrix against the available vector before granting a request.

Semaphores
A semaphore S is an integer variable accessed only through wait(S) and signal(S). Binary
semaphores act as mutex locks around the critical section.
"""

# Expected outcome for every topic the syllabus parser produces.
# A set lists the acceptable videos for the path; an empty set marks a gap.
EXPECTED: dict[str, set[str]] = {
    "Concept of Operating Systems": {"osIntro0001"},
    "System Calls": {"osSyscall02"},
    "Structure of an OS": {"osSyscall02"},
    "Structure of an OS: Monolithic": {"osSyscall02"},
    "Structure of an OS: Microkernel": {"osSyscall02"},
    "Process states": {"osProcess03"},
    "Process Control Block (PCB)": {"osProcess03"},
    "Context switching": {"osProcess03"},
    "Threads": {"rvThreads04"},
    "CPU Scheduling": {"osSched0004", "osRoundRob5"},
    "CPU Scheduling: FCFS": {"osSched0004"},
    "CPU Scheduling: SJF": {"osSched0004"},
    "CPU Scheduling: Round Robin": {"osRoundRob5"},
    "Critical section problem": {"osSync00006"},
    "Semaphores": {"osSync00006"},
    "Necessary conditions for deadlock": {"osDeadlock7", "rvDeadlock1"},
    "Deadlock prevention": {"osDeadlock7"},
    "Banker's algorithm": {"osBankers08", "rvDeadlock1"},
    "Paging": {"osPaging009"},
    "Segmentation": {"rvSegment02"},
    "Virtual memory": {"osVirtual10"},
    "Demand paging": {"osVirtual10"},
    "Page replacement algorithms": {"osVirtual10"},
    "Disk scheduling": {"rvDisk00003"},
    "File allocation methods": {"rvFiles0005"},
    "RAID levels": set(),
    "Access control lists": set(),
    "Public key cryptography": set(),
}
