Based on my research, here's a comprehensive overview of Answer Set Programming approaches to multi-party calendar scheduling:

## Generalized Approaches in the Literature

### 1. **Constraint Satisfaction & Distributed Valued CSP (DVCSP)**

The foundational approach treats meeting scheduling as a **Distributed Valued Constraint Satisfaction Problem**[1]. This framework:

- Assigns **weights/valuations** to constraints reflecting their importance
- Allows **constraint relaxation** based on priority when problems are over-constrained
- Searches for solutions that satisfy as many important constraints as possible
- Supports distributed agents representing individual participants' calendars

Key insight: Not all constraints are equally important. The system can relax lower-priority constraints (e.g., preferred times) while maintaining hard constraints (e.g., participant availability).

### 2. **ASP-Specific Encoding Patterns**

Answer Set Programming has been successfully applied to scheduling since 2017, particularly in healthcare[2]. Core patterns include:

**Problem Decomposition:**
- **Master Problem**: Assigns high-level scheduling decisions (e.g., which days)
- **Sub-problems**: Handle detailed assignments (e.g., specific times, resources)

**Logic-Based Benders Decomposition (LBBD):**
- Guarantees optimality while improving performance through decomposition
- Master problem proposes solutions; sub-problems validate feasibility
- Iterative feedback loop refines solutions until optimal

### 3. **Multi-Shot Solving for Scalability**

Critical for handling scaling issues you're experiencing[2]:

- **Incremental constraint addition**: Start with target schedule, gradually relax constraints if no solution exists
- **Reduces grounding overhead**: Avoids computing all possible combinations upfront
- **Iterative solving**: Add one time window/constraint per iteration until solution found
- **Parallel execution**: Independent sub-problems can be solved concurrently

Example: For periodic scheduling, try optimal week first; if unsolvable, increment/decrement target week iteratively rather than grounding entire search space at once.

### 4. **Scalability Techniques**

**Pre-processing optimizations:**
- Compute and exclude infeasible time slots before solving (e.g., when all participants unavailable)
- Reduces search space by 30-50% in practice[2]

**Rolling horizon approaches:**
- Solve week-by-week with long-term memory
- Ensures mid-term constraints (e.g., no more than 2 weekend meetings per month) while managing complexity

**Density-aware strategies:**
- Problem difficulty correlates with "service density" (meetings per participant per day)
- Higher density requires decomposition; lower density can use monolithic approaches

## Available Codebases and Workflow Integration

### 1. **Potassco/Clingo Ecosystem** (Primary ASP Tool)

**Clingo** is the reference ASP solver from University of Potsdam:

- **Repository**: Available at potassco.org
- **Documentation**: Comprehensive guides at [3]
- **Python API**: Embedded Python support for hybrid solving[4]

**Example implementations:**
- Train scheduling with clingo-dl: https://github.com/potassco/train-scheduling-with-clingo-dl[5]
- Shows ASP encoding patterns, solution checking, and benchmark scripts

**Workflow position**: Core solver - processes ASP encodings and returns optimal solutions

### 2. **LUNCH Course Scheduling System**

**Repository**: Open-source ASP-based scheduling tool[6]

- **Purpose**: Course timetabling with complex constraints
- **Technology**: Uses Clingo for solving
- **Extensibility**: Modular constraint definition in high-level ASP syntax
- **License**: Free and open-source

**Workflow position**: Reference implementation showing complete pipeline from requirements to solution

### 3. **Constraint Programming Alternatives**

**Google OR-Tools CP-SAT**:
- Open-source constraint programming solver[7][8]
- Excellent for scheduling problems with heterogeneous constraints
- Python/C++/Java APIs
- Strong performance on employee scheduling benchmarks

**Workflow position**: Alternative approach if ASP scaling issues persist

**OptaPlanner** (Java-based):
- Open-source AI constraint solver[9]
- Designed for maintenance scheduling, employee rostering
- Real-time rescheduling support (handles sick days, cancellations)
- REST API available

**Workflow position**: Production-ready alternative with built-in rescheduling

**Timefold** (OptaPlanner successor):
- Employee scheduling quickstarts: https://github.com/TimefoldAI/timefold-quickstarts[10]
- Over 50 out-of-box constraints for scheduling
- Apache License (commercial-friendly)

**Workflow position**: Drop-in solution if you need rapid deployment

### 4. **PyJobShop**

**Repository**: https://github.com/PyJobShop/PyJobShop[11]

- **Purpose**: Python library for scheduling with constraint programming
- **Technology**: Wraps CP solvers with Pythonic API
- **Use case**: Job shop scheduling (similar constraint structure to calendar scheduling)

**Workflow position**: Python middleware layer - simplifies constraint definition

## Recommended Workflow Architecture

Based on the literature, here's how these components fit together:

```
[Input Layer]
  ↓
  Calendar data, participant availability, preferences
  ↓
[Pre-processing]
  ↓
  - Identify infeasible time slots
  - Compute constraint weights/priorities
  - Calculate problem density
  ↓
[Decomposition Strategy Selection]
  ↓
  Low density → Monolithic ASP encoding
  High density → LBBD or Multi-shot
  ↓
[ASP Encoding] (using Clingo/Potassco)
  ↓
  - Master problem: Day assignment
  - Sub-problems: Time + resource assignment
  ↓
[Multi-shot Solver]
  ↓
  - Iterate with relaxed constraints if no solution
  - Parallel execution of independent sub-problems
  ↓
[Solution Validation & Post-processing]
  ↓
  - Check solution quality
  - Generate human-readable schedules
  ↓
[Output/Integration Layer]
```

## Addressing Your Scaling Issues

**Immediate actions:**

1. **Implement multi-shot solving**: Don't ground entire search space upfront. Start with tight constraints, iteratively relax.

2. **Add pre-processing**: Compute participant intersection periods before invoking solver. This dramatically reduces variables.

3. **Decompose temporally**: 
   - Master: Assign meetings to days
   - Sub-problems: Assign specific times within each day
   - Far more scalable than monolithic approach

4. **Consider LBBD**: If optimality is critical and you're hitting scaling limits, Logic-Based Benders Decomposition provides best balance of optimality and performance.

5. **Parallel execution**: Use Clingo's `--parallel-mode` option for independent sub-problems.

**Experimental comparison** from healthcare scheduling[2]:
- Monolithic ASP: Timeout on problems with >0.45 service density
- LBBD with multi-shot: Solved 100% of instances with <0.6 density
- Multi-shot alone reduced solve time by 50-70%

**Key insight for calendar scheduling**: Your "density" = (number of required meetings) / (available time slots × participants). If density > 0.4, you likely need decomposition approaches rather than monolithic ASP encoding.

Would you like me to elaborate on any specific technique or provide example ASP encodings for calendar scheduling constraints?

Sources
[1] [PDF] Scheduling Meetings using Distributed Valued Constraint ... https://frontiersinai.com/ecai/ecai2000/pdf/p0383.pdf
[2] [PDF] Recent Answer Set Programming Applications to Scheduling ... https://ceur-ws.org/Vol-3883/paper3_RCRA8.pdf
[3] [PDF] A User's Guide to gringo, clasp, clingo, and iclingo http://wp.doc.ic.ac.uk/arusso/wp-content/uploads/sites/47/2015/01/clingo_guide.pdf
[4] clingo API documentation - Potassco https://potassco.org/clingo/python-api/5.5/clingo/
[5] potassco/train-scheduling-with-clingo-dl - GitHub https://github.com/potassco/train-scheduling-with-clingo-dl
[6] [PDF] LUNCH: an Answer Set Programming System for Course Scheduling https://sol.sbc.org.br/index.php/eniac/article/download/25756/25572/
[7] A practical introduction to Constraint Programming using CP-SAT ... https://pganalyze.com/blog/a-practical-introduction-to-constraint-programming-using-cp-sat
[8] Constraint Optimization | OR-Tools - Google for Developers https://developers.google.com/optimization/cp
[9] OptaPlanner - A fast, easy-to-use, open source AI constraint solver ... https://www.youtube.com/watch?v=bIvt9z-zVHo
[10] How feasible it is to develop a constraint solver without a math ... https://www.reddit.com/r/ExperiencedDevs/comments/1hm3bg0/how_feasible_it_is_to_develop_a_constraint_solver/
[11] PyJobShop/PyJobShop: Solve scheduling problems with constraint ... https://github.com/PyJobShop/PyJobShop
[12] [PDF] Answer-Set Programming for Lexicographical Makespan ... https://proceedings.kr.org/2021/27/kr2021-0027-eiter-et-al.pdf
[13] Algorithm to find meeting time slots where all participants are available https://stackoverflow.com/questions/34425237/algorithm-to-find-meeting-time-slots-where-all-participants-are-available
[14] AI Scheduling Algorithms: Constraint Satisfaction For Workforce ... https://www.myshyft.com/blog/constraint-satisfaction-problems/
[15] [PDF] Matchmaking with Answer Set Programming - Universität Potsdam https://www.cs.uni-potsdam.de/wv/publications/DBLP_conf/lpnmr/GebserGSS13.pdf
[16] A generic approach to conference scheduling with integer ... https://www.sciencedirect.com/science/article/pii/S0377221724002601
[17] Automated Optimization of Programs and Processing Tools in ... https://www.cs.uky.edu/ASPEncodingOptimization/
[18] [PDF] Answer Set Programming: A tour from the basics to advanced ... https://www.mat.unical.it/ricca/downloads/aspapps.pdf
[19] Scheduling meetings using distributed valued constraint satisfaction ... https://dl.acm.org/doi/10.5555/3006433.3006514
[20] Adaptive large-neighbourhood search for optimisation in answer-set ... https://www.sciencedirect.com/science/article/pii/S0004370224001668
[21] Benchmarking Answer Set Programming systems for resource ... https://www.sciencedirect.com/science/article/pii/S0957417422009101
[22] [PDF] CONSTRAINT-BASED PLANNING AND SCHEDULING https://icaps12.icaps-conference.org/planningschool/slides-Bartak.pdf
[23] Answer Set Planning: A Survey | Theory and Practice of Logic ... https://www.cambridge.org/core/journals/theory-and-practice-of-logic-programming/article/answer-set-planning-a-survey/7373A95362A4A45C399810910AC6D732
[24] Answer-Set Programming for Lexicographical Makespan ... - arXiv https://arxiv.org/abs/2212.09077
[25] [PDF] Applying Constraint Satisfaction Techniques to Job Shop Scheduling https://www.ri.cmu.edu/pub_files/pub1/cheng_cheng_chung_1995_1/cheng_cheng_chung_1995_1.pdf
[26] [PDF] Evaluation Techniques and Systems for Answer Set Programming https://www.ijcai.org/proceedings/2018/0769.pdf
[27] c# - Schedule with Constraints - Stack Overflow https://stackoverflow.com/questions/44452574/schedule-with-constraints
[28] [PDF] Integrating Answer Set Programming and Constraint Logic ... https://www.depts.ttu.edu/cs/research/documents/46.pdf
[29] ASP.NET Core Resource-Scheduling Calendar (Open-Source) https://code.daypilot.org/20604/asp-net-core-resource-calendar-open-source
[30] [PDF] An AI Approach to Large-Scale Medical Appointment (Re ... https://ceur-ws.org/Vol-3495/paper_04.pdf
[31] dhtmlxScheduler with ASP.NET Core Scheduler Docs https://docs.dhtmlx.com/scheduler/howtostart_dotnet_core.html
[32] Best way to create an MVC 4 Timetable/Calendar/Scheduler https://stackoverflow.com/questions/28948501/best-way-to-create-an-mvc-4-timetable-calendar-scheduler
[33] Build an appointment scheduling app! - YouTube https://www.youtube.com/watch?v=wkO12Wm6w9w
[34] Calendar appointment app Backend using ASP.NET Web API - GitHub https://github.com/prakash-s-2210/calendar-appointment-app-dotnet
[35] ASP.NET MVC Integrate Google Calendar in Telerik UI Scheduler https://www.telerik.com/aspnet-mvc/documentation/knowledge-base/scheduler-google-calendar-integration
[36] constraint programming - Timetabling/Scheduling Library https://stackoverflow.com/questions/33682552/timetabling-scheduling-library
[37] DevExpress-Examples/asp-net-mvc-scheduler-custom-go-to-date ... https://github.com/DevExpress-Examples/asp-net-mvc-scheduler-custom-go-to-date-dialog
[38] DayPilotCode/daypilot-asp.net-core-monthly-calendar - GitHub https://github.com/DayPilotCode/daypilot-asp.net-core-monthly-calendar
[39] [PDF] A Tutorial on Hybrid Answer Set Solving with clingo https://www.cs.uni-potsdam.de/~torsten/hybris.pdf
