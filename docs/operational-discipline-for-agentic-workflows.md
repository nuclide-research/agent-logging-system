# Operational Discipline for Agentic Workflows

What multi-agent AI can borrow from the industrial control room.

## Abstract

Multi-agent AI systems fan work out across many agents, and they have almost no operational discipline. Agents degrade in slow ways. They fail without attribution. The observability built for web services does not map cleanly onto them. Industrial control rooms solved the same class of problem decades ago, for physical processes that must not fail. We took the operator's discipline, mapped it onto a fleet of agents, built it, and tested it on real runs. The build taught us four lessons, and the data corrected our design twice. This is the argument and the evidence.

## The problem

An orchestrator dispatches subagents. Some retrieve, some execute, one integrates the result. The work fans out, runs in parallel, and comes back. When it works, it is fast. When it does not, you often find out late.

Agent failures are quiet. A retrieval lane slows from one second to nine and the run still completes, just worse. A subagent's error rate climbs and the orchestrator keeps dispatching. One agent in a fan-out is the bottleneck and nothing says which one. The failure is a slope, not a cliff, and a slope is easy to miss while you watch the final answer.

The tools we have do not fit. Request tracing and service metrics were built for stateless calls where latency and status codes carry most of the meaning. An agent has semantic state on top of that: a confidence, a task it is part way through, a reasoning step that may have drifted from its source. A 12-second turn can be healthy or broken, and the duration alone will not tell you which.

We do not lack logs. We lack the discipline to read them.

## The source

A power plant runs on three systems. AVEVA PI is the historian. It records every sensor reading, dozens a second, and keeps years of it. Siemens WinCC is the operator console. It shows the live state and raises an alarm when a value crosses a limit. IBM Maximo holds the maintenance history and schedules what to fix next.

The systems matter less than the operator. A good operator does not watch one live number. They read the trend. They keep a written log and hand it off at shift change. They walk the floor and listen. A sensor can read normal while a pump starves. They catch a failing bearing weeks before it seizes. They read it in a slow climb of vibration and a few degrees of extra heat.

The discipline has a shape. Watch the trend, not the snapshot. Alarm on deviation from normal, not on a fixed number. Keep a structured record. Pair the alarm with the response. Catch degradation before it becomes failure. None of this is exotic. It is the boring, load-bearing practice that keeps a plant running, and a fleet of agents needs it just as much.

## The transfer

The pattern maps cleanly onto agents.

| Control room | Agent fleet |
|--------------|-------------|
| one sensor reading | a structured observation an agent emits |
| the historian | a rolling per-agent state with trends |
| the WinCC alarm engine | a rule that trips on deviation |
| the operator's response procedure | an alarm mapped to a concrete action |
| the console | one surface to ingest and then query |

An agent emits an observation per action: a timestamp, what it did, how long it took, whether it worked, how sure it was. The historian keeps a bounded window per agent and computes the trend. The alarm engine runs threshold rules over that state. When a rule trips, it carries a recommended action. The console gives you one place to feed observations in and read the fleet's state out.

We built this as a small Python library, `agent-logging-system`. We did not build it for the library. We built it to find out what the discipline requires once it meets real data.

## Four lessons from the build

### 1. A threshold has to be relative to normal

Our first latency alarm used a fixed line: trip over five seconds. It passed every test. Then we replayed a real session through it. It raised two false alarms. Both were long explanations, flagged as slow. They were not slow. They were long on purpose.

The fix is the operator's rule. A boiler at 200F is fine. A cooling tower at 200F is an emergency. Same number, different baseline. The alarm now compares each agent against its own established normal and trips on a sharp deviation from it. An agent that runs slow but steady stays quiet. A jump from one second to nine still trips. Two guards keep it honest. You cannot judge a deviation from a single sample, so there is a warmup. A one microsecond to fifty microsecond blip is a large ratio and means nothing, so there is an absolute floor.

### 2. Latency has a type

The baseline rule helped, and it hid a deeper error. We ran the monitor on itself, with real timings, and its own method calls took microseconds and never tripped. That exposed the real problem. The latency field had been carrying two different quantities under one name.

Execution time and generation wall-clock are not the same thing. A nine second API call that should take one second is a problem. A nine second answer that was meant to be long is not. Reading them as one number is a type error wearing a number's clothing. So we split them in the schema. Every observation declares its latency kind. A duration tagged as generation can no longer reach the machine alarm, at any size. Mixing them is now impossible to express. That is stronger than a threshold that happens to handle it.

### 3. The monitor must be cheap on the hot path

A monitor that slows the thing it watches will be turned off. Ingesting an observation has to stay near free. It happens on every action. Reading the fleet state happens far less often and can cost more.

We measured it on the self-monitor. Ingest runs in about two microseconds and only marks the agent changed. A full scan re-evaluates only the agents that changed since the last scan, so a clean agent is never re-checked. For five agents a scan ran in fifteen to twenty-seven microseconds. It scales with the number of changed agents times the number of rules. The rule for a large fleet falls out of the measurement. Ingest every event. Let the scan pay only for what changed.

### 4. Attribution needs the right grain

In a fan-out, the obvious move is one agent record per subagent. It does not work. A subagent is dispatched once. It never builds a baseline. A single slow call cannot be judged against a history that does not exist.

The grain that works is the lane. Group dispatches by tier: a Sonnet retrieval lane, a Haiku execution lane. The lane accumulates a baseline across many dispatches, and a dispatch that deviates from the lane's normal trips. A lane carrying heavy clean volume raises a separate, quieter signal that says to parallelize it. The orchestrator's own integration turn is generation, so a long synthesis never alarms. One run lights up the slow lane and stays silent on the healthy ones and on the long, expected synthesis.

## The lesson under the lessons

We did not reason our way to any of this. We built a reasonable first version, pointed it at a real session, and the false alarms told us the threshold was wrong. We pointed it at itself and the microseconds told us the type was wrong. Each version got better by running against something real. Harder thinking in the abstract did not produce the fixes. Measurement did.

That is the same principle the control room runs on. Trust the trend you measured, not the spec sheet. An operator who believes the gauge over the sound of the pump loses the pump. We believed the real stream over our design intent, and the stream was right both times.

## Why it improves performance

The payoff is the operator's payoff, moved onto agents.

You see a lane slow down while the run is still going. You throttle it or raise its timeout before the whole job drags. You see an error rate climb on one tier and you stop feeding it before the failures compound. You see which lane is the bottleneck in a fan-out, by name, instead of guessing. You keep a structured record of what every agent did, so a bad run can be read back instead of reconstructed. The recommendation comes with the alarm, so the signal names a response.

None of this makes a single agent smarter. It makes a fleet legible. A legible fleet fails less, fails slower, and fails where you can see it. That is the whole return on operational discipline, and it is why plants run it on processes they cannot afford to lose.

## What this is not

It is a young tool and a narrow claim. The library is in-memory and single-process. It does not replace request tracing or service metrics. It works alongside them, on the layer those tools were not built for. The orchestrator adapter is validated on simulated dispatch timings, not yet wired to a live fan-out. The rule set is small on purpose, with three default alarms and a seam for your own.

The argument is larger than the tool. Agentic systems are being built fast, and the discipline for running them in production is thin. The control room is a working model of that discipline, proven on processes where failure is not an option. Borrowing it is cheap. We borrowed a small part, and the small part already catches the failures we used to find late.

## Notes

The tool is `agent-logging-system`, in this repository. The four lessons map to versions 0.1 through 0.4 in the commit history. The measurements come from `examples/self_monitor.py`, the false alarms from `examples/session_replay.py`, and the fan-out behavior from `examples/orchestrator_integration.py`. Every number here is reproducible by running those files.
