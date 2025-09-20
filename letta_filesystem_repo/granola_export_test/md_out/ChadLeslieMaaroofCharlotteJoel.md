

**Chad/Leslie/Maaroof/Charlotte/Joel**
======================================

Attendees:

joel.sadler@glef.org,charlotte.luongo@glef.org,maaroof.fakhri@glef.org,lbondaryk@concord.org

2025\-08\-21T12:00:00\-04:00

\-\-\-\-

\#\#\# Thermal Transfer Simulation Development

\- Leslie rotated ground sim 90 degrees to create wall\-based heat transfer model

\- Required 3\+ hour Slack discussion on boundary conditions

\- Invisible room walls needed for proper atom containment and temperature measurement

\- Small tweaks create cascading effects requiring physics expertise

\- Current sim shows solar radiation hitting wall vs ground

\- Demonstrates radiative heat transfer from sun to surfaces

\- Next version needs enclosed room with temperature sensors inside

\#\#\# Educational Goals \& Simplification

\- Target: middle school intuitive understanding of window vs wall thermal differences

\- Level 1: Students recognize windows allow more direct heat transfer than walls

\- Building toward full radiation/conduction/convection comprehension for house design

\- Charlotte’s pedagogical priorities:

\- Direct solar radiation through windows vs indirect IR from heated walls

\- Time scale comparison (couple hours direct sunlight exposure)

\- Relative heating rates, not exact formulas or magnitudes

\- Agreed to focus on two key effects initially:

\- Direct radiative heating through transparent materials

\- Indirect heating from wall IR radiation

\#\#\# Assessment Integration Discussion

\- Leslie shared Massachusetts/California simulation\-based testing research

\- Students averaged 20\-50 sim runs per assessment despite time constraints

\- Tests measure DOK level 3 performance vs traditional multiple choice

\- California implemented at scale since 2017\-2018

\- Joel seeking efficacy data for randomized controlled trials

\- Wants evidence that sim\-based assessment outperforms traditional methods

\- Important for publisher conversations and standards adoption

\- Assessment path provides validation for curriculum approach

\- Links project\-based learning to measurable outcomes

\- Creates bridge to future standardized testing evolution

\#\#\# Technical Implementation Status

\- Leslie will have working prototype ready next week for Joel’s team to embed

\- Temperature sensors and time display needed in interface

\- UI/feedback system collaboration offered between teams

\- 27 additional features expected after initial version

\- Boundary condition complexity manageable but requires ongoing physics discussions

\#\#\# Next Steps

\- \*\*Joel\*\*: Schedule follow\-up meeting August 28th, 1\-2pm Eastern

\- Will include Scott (engineer) for direct technical coordination

\- Leslie will use time normally allocated to different meeting

\- \*\*Leslie\*\*: Deliver embeddable prototype by next week

\- \*\*Team\*\*: Continue refining pedagogical priorities for subsequent sim variations

\-\-\-

Chat with meeting transcript: \[https://notes.granola.ai/d/d5195403\-bc74\-4249\-8e69\-65e074726f94?source\=zapier](https://notes.granola.ai/d/d5195403\-bc74\-4249\-8e69\-65e074726f94?source\=zapier)

\=\=\=\=\=\=\=\=

\-\-\-\-

Granola link: https://notes.granola.ai/d/d5195403\-bc74\-4249\-8e69\-65e074726f94

\=\=\=\=\=\=\=\=

Transcript:

Me: Alright. I'll just chatted a little squib of

Them: Yes.

Me: my thoughts.

Them: Hi, folks.

Me: Hello.

Them: Hi, Maaroof. Hello.

Me: Going well. Yourself?

Them: How's it going? God. I just got back from vacation, so I'm very much

Me: Oh. I don't know. Welcome back. Where was vacation?

Them: Ireland.

Me: Okay. That's not bad. Oh, that's

Them: And Denmark. Copenhagen.

Me: that's fun.

Them: So yeah, it was it was good. Super warm. Great weather.

Me: Mhmm.

Them: Leave for Ireland.

Me: Yeah. Right. I'm gonna say.

Them: Unusual. But I that's the story of the

Me: Yeah.

Them: these days. Oh, okay.

Me: Yes.

Them: While I was traveling, I I get these weather alerts

Me: No. Alright.

Them: about Zurich. Where I live, and it's like, one day, it's a heat wave. The next day, it's a heat wave. Next day, it's flooding rains. The river's rising.

Me: Oh my god.

Them: And then the next day, it's a heat wave again. And then it's flood, flood, flood. It's then heat wave is like, okay.

Me: Uh\-huh. Yeah. Stay in Ireland.

Them: You don't notice it when you're in it. Yeah. And then now it's now I'm in Ireland.

Me: Yeah.

Them: And it's balmy.

Me: Yeah.

Them: It should be rainy. So all good.

Me: Yes.

Them: Things with you guys.

Me: Charlotte's coming in here as well. Hey, Charlotte.

Them: Good. I'm trying to trying to get you guys what you need until for for the next two weeks until I'm in Europe. Oh, cool. Where are going? We're taking one of those river cruises, so from Basel to Amsterdam.

Me: Cool.

Them: Nice. Is that the the Lima or the ten day? That's the one that is It's the Ryan. Okay. Yeah. Yeah. It's yeah. Should really know all three of the names. They come up in trivia every week.

Me: Yeah. Right.

Them: But

Me: And

Them: up 1,001\. It goes which way.

Me: right. Yeah. It's so easy to do this.

Them: Oh, cool.

Me: Like it's like Europeans with US states. We just don't know them.

Them: Great. Basel is beautiful. I hope you get some time there before you jump on the river. Oh, absolutely. It's very nice. Great. So agenda

Me: Yeah. So we all met a little bit earlier this week, which was sort of

Them: Yep.

Me: was sort of recognized, oh, I guess we have another meeting, which is not bad to calibrate, but we may have maybe bring you up to speed as much as as anybody, which is fine.

Them: Okay.

Me: But like Leslie said, we've been diving in already and got some ideas and questions and things that are probably worth calibrating on. And

Them: Sweet.

Me: we don't need the whole time we slot it in. That's fine too.

Them: Yeah. That's fine. I I caught up a job before, and also mentioned that, yeah, you guys met already this week. So because the time is already in the calendar, just thought Hello. And then smile, and then we can go our separate ways and and get back to it. Maybe if there's any specific you you do wanna touch base on now, then Yeah. That's fine. But otherwise, we can we don't have to the time.

Me: Yeah. We were digging a little bit. We had a few a few sort of points and not not detailed, but

Them: Yeah. I mean, the well, two so two things. One, to to follow on in the conversation that we had last time, Joel, about, like, how easy is it for somebody to just go ahead and use We have, like, you know, this little viewer and and and make a make a SIM thing. Right? Can you can you do that? And I am I reconfirmed for myself in the process of trying to kick start the thing that you asked for. Why that is not trivial. Because, you know, I said, well, so take this ground sim and move it the layer of atoms over. So that there's stuff on either side, and then make it behave like different kinds of materials on a switch. Sounds super easy. Right? No. Well, ensued was a three hour long asynchronous Slack conversation that scrolled for pages and pages about, you know, how you how you make a room that you can't see because you're looking at a microscopic piece of it, and yet you need an enclosed space with particular characteristics of reflection and absorption on the walls of the room so that the atoms that are inside it actually stay inside it and heat up the way that they're supposed to. So that you can measure what the temperature is in the room even though

Me: Right.

Them: only you're seeing a piece that is the big of it. And that's the sort of thing that's kind of, like, hard to it's hard to even, like, premeditate much less express in a set of documentation instructions that would allow other people to successfully build these kinds of sims and have them work the way we intend for them too. There's some boundary conditions that need to be

Me: Yeah. Yeah. I mean, it's it's this interesting combination

Them: sort of not into

Me: of, you know, nuances of configuration sort of could large scale paradigm that are built into the simulation. And then I think equally parallel you know, scientific conversation because all of a sudden you start to say, oh, well, what does it what does temperature really mean here actually? And what are we trying to get at in terms of the idea? Because you know, really, you could make it absorb, but you kinda don't want it to absorb. You know, these kinds of things. And so it's very it's very interesting.

Them: I can

Me: Nicely geeky. We all get absorbed in it.

Them: small even small tweaks is what I'm hearing could cause some cascading you know, I used to do finite element stuff for

Me: Right.

Them: know, wound healing, Sure. Thermal stuff, right, for Apple. You know, it was, like, a lot of ther so, yeah, it off just getting the right boundary condition is really tricky. You often need a PhD in their home.

Me: Yeah. Right. Yeah.

Them: And and it intersects with, like, what we happen to have

Me: Right. Right.

Them: have instrumented as a command that you can give. Right.

Me: Mhmm.

Them: That work. Right? So there's a little bit of, like, finessing based on just previous knowledge of the system, and then there's a little bit of physics. Oh, okay. You know? And

Me: Yeah.

Them: then were the questions that eventually I really wanna be putting to Charlotte about you know, do you want all of these effects at the same time? Is this confusing? Right? Like, there's potentially quite a lot of stuff going on here. In terms of absorption, reflection. You know, do you do we care to document the fact that when the IR is reradiated, which it only is in some of the cases, from the molecules inside the room, that it can then either be reflected or absorbed inside the glass or the brick wall. Do we care about, you know, propagating the heat across the brick wall slowly over time and showing that, yes, the room will eventually heat up in that case too. How long a time are we, you know, dealing with here? Right? Like, we could do all of these things. Probably, you don't want us to in this very early version because, again, we're mostly trying to see if we can a couple of cases and have it switch in the way that you want it to. But over time, if we like this thing, we're gonna need to spend a little bit more time deciding are there two versions? Are there five versions? How many things can the kids switch? How many effects do you want them to show, or maybe you let them turn them on and off? Or maybe it's scaffolded as they get into it? Right? Like, there's a lot.

Me: Yeah. Yeah. And it's and

Them: It's interest all interesting. Right?

Me: yeah. I know. It's great stuff, and and, you know, there's no question that you know, we can do the things that we're aiming for. And when you get into the next layer of questions because you're working at that level, that's when it gets really interesting. I'm sure you were seeing this when you were thinking about the pathways in the cells and what it you know, all of a sudden, you're like, wait a minute. What's really going on? And what do we wanna show? And those might or may not be the same thing. I mean, you can get into existential questions about what reflection really is because it's actually absorption and readmissions of, but not really. And into sort of these questions about transfer. So on the one hand, you can get lost in that. On the other hand, you can bring out questions that normally get brushed under the rug, like the nature of how different types of radiation, you know, relate to temperature. Which most of the time you just memorize conducting infection radiation and move on. But, you know, when you can see it, you can actually say, oh, it's the IR radiation that is sometimes being absorbed here and then bouncing around the room. That's what you feel in the window, and that's what you and so we can get into some interesting questions about how you wanna play that into house design as we go along. So

Them: So it might be helpful since Maaroof is in the room So I don't think visually we've my probably that we just pull up, like, the screenshot of just what we're even talking about here because it's I think we I think layperson's summary is we had a sim that we're like, alright. Let's tweak this. And of this way, let's turn it that way. Right? And I'm hearing you, Leslie. Oh, turning it that way, actually.

Me: Yeah. Right. Yeah. That's a good good point. Right? Since the roof is just yeah.

Them: To Turning it that

Me: No. It's

Them: way has impact putting putting measurable and, you know, specifiable content on either side of it has impact. Right?

Me: Yeah. It's it's doable it's doable, but it raises interesting questions, think, is the

Them: Yeah. So not surprising.

Me: is the intriguing stuff.

Them: And if we have the original, just so we see, it's like, hey. This is what we you know, here's what's the starting point, and this is, the what if since question of the the link just below there. Was the, is it original SIM? Yep. And Yeah. Just preview. So, you know, it's sort of this is, like, what we what we get at that link. And in order to get it to something that we could use in our tiny house particular question there, you know, those clicks and you know, are all the simulated thing. Plus, like, there was a orientation change because at the ground and instead of a wall that we were hoping. So this sim, you know, beautifully demonstrates what is radiative heat transfer starting to be all about starting from the sun to the to your wall? And Yeah. So this is was a mock up, and then our what Leslie is talking about is, hey. What's involved with just taking that thing, tweaking it to that box that we would just pop up in our

Me: Mhmm.

Them: in our prototype. Got it.

Me: Yeah. We're getting to interest I mean, so just so you're brainstorming about them as you go along. You know, some of the interesting questions that are, I think, meta questions are know, is there is the are the ultimate interests, you know, what is one set of them about seeing a room with a glass window heat up versus something like a brick wall? We're talking about a brick wall, what are the nuances that we're trying to get across with the the heating or not heating of a wall and how that affects the room, You know, what about energy, you know, forms, so to speak, or or types, and how is that important? Where is it useful and not useful to emphasize the

Them: Mhmm.

Me: that these are being absorbed in I mean, it's a quantum model here, right, which is great and also you know? So I haven't thought about that part at all. So

Them: Yeah. I mean, we could sit down and go

Me: Right.

Them: through once we have all these, like, questions laid out. Go through and nail it for a middle school audience.

Me: Exactly. Yep.

Them: I'm not too worried because you only go so far with a middle

Me: Exactly. Yep.

Them: audience. Right? And and we can do, you know, relatively simplified things like, okay, in a typical situation, this percentage of the energy is going to radiate in the room, and this percentage will bounce off walls. And you know, just kind of stick with that kind of concept.

Me: Yeah.

Them: And simplify things in that way. And this is so for this particular simulation, like ideally, we would take the world where you can turn off and on different forms of thermal energy transfer. But for this particular simulation, we're really going to focus on two things. One, how can a house heat up? Just by sitting in the sun? And so radiative thermal energy transfer, and then when you get a that's heated up through thermal energy transfer, or you're getting thermal energy transfer coming into the house what is causing the house temperature to rise? So it's the direct heating from the radiation when you've got something like a window, and then it's indirect because you're getting infrared being given off by the wall.

Me: Yep.

Them: And what's gonna be faster?

Me: No.

Them: Like, we don't need the exact formula of just how fast, you know, and oh if it sits here for twenty four hours in the sun, which it never would, you know? So what we need is, okay, relative what's gonna be the fastest way to heat the indoor space of the house? Well, obviously direct radiation. Versus the wall. Will you get some heat from infrared radiation from the wall? Yeah. Of course you will. So, like, we're looking for comparisons more than exact

Me: Yeah.

Them: itudes for middle

Me: That's great. And that's good because we can't really get exact anyway.

Them: Alright. Right. And I'm and I'm hearing that we need to be returning or displaying or something, the time it takes in addition to the temperature measurement, which we hadn't really, like,

Me: Yeah.

Them: doesn't show up in this drawing, but Yeah.

Me: It's

Them: That would be that would be good. We're trying to keep it simple for this for

Me: Yeah. Exactly. I mean, just know know that there's the ability to

Them: You know, like, a lot of these things would be

Me: make graphs and and, yeah, we need to think about what they mean if you're gonna do that. So exactly.

Them: Exactly. So, like, we would love

Me: Mhmm.

Them: time. And even if it's not like, an exact time where you see a clock counting down, even if it's just something that kind of gives you a sense of time scale,

Me: Yeah.

Them: over the course of a couple of hours,

Me: Mhmm.

Them: Mhmm. Because we can assume that for most locations on the planet, in most situations, it's just gonna be a couple of hours that a wall would get direct sunlight.

Me: Right.

Them: Mhmm. And so, you know, a couple of hours go by, and and what what we're trying to see here is okay a couple of hours in direct sunlight with all of the solar radiation coming directly into the house and thus being able to be absorbed by the floor or the air in the house. Directly, you're gonna get temperature increases much faster than if it's any solid surface, and of course there's gonna be some solid surfaces like brick that it's gonna take a really long time for the infrared energy to start to radiate into the house. And then other substances, like, let's say that we had, like, a very thin wall with aluminum siding, Well, that's gonna heat up faster, but at this point, we're not talking about different materials.

Me: Okay.

Them: What we're really trying to portray is, okay, we've got something that's opaque, The solar energy isn't directly coming through into the house. Versus something transparent. Where it is directly coming in. So we've got a difference between like direct radiative energy versus you're entirely shaded. By this surface. And so the only heat that you're actually gonna get from the solar energy that hitting your house is through infrared that's given off by that wall.

Me: That's super helpful. Those are some of the

Them: Mhmm.

Me: questions we were, you know, grappling with is sort of how do you portray and and what do you prioritize in those?

Them: Yeah. And for a context least Maaroof with Noah, our game designer, you know, level one you know, is really we're happy if kids can describe with intuition, hey. A window versus a wall is gonna make a difference thermally because windows allowing these these it's allowing this energy transfer that's coming from the sun.

Me: Mhmm.

Them: Ultimately. And that's all, you know, every anything beyond that level one is not stuff we need to answer right

Me: Great idea. Mhmm. Mhmm.

Them: now. Yeah. We Okay. And that's what middle schoolers would need to know. At them

Me: No.

Them: like, maximum or is that just a Oh, no. Just as a starting. Just as a starting point. Just as a starting point. Yeah. For sure. Because what we're building them up to is, like, a complete understanding, not a complete That was the wrong word there. A solid enough understanding of the differences between radiation, conduction, and convection that they can compile like the three modes of thermal transfer to to create a house that's as energy efficient as possible within their knowledge set. So what we're wanting them you guys know the performance expectation, I'm sure, really, really well, where students need to design a device that is either going to increase or decrease amount of thermal energy transfer between the protected internal environment and the

Me: Mhmm.

Them: environment. So what's our device here? It's a house.

Me: Mhmm.

Them: That's it.

Me: Yep.

Them: Yeah.

Me: Yeah. And the ideal situation that normally is the best thing people don't get to is if you can do that with intent realizing that you're using those principles as design You know, I'm using the combination of radiation and convection as a tool for myself to heat this place up. Right? And, normally, that's sort of

Them: Mhmm.

Me: you memorize, you you describe the definitions of the three. Make a cool house out of, you know, cardboard, and then you check off the box and go on to the next

Them: Right.

Me: unit. Right?

Them: Yeah. But here, we're, like, really wanting them to understand the difference between the

Me: I Mhmm.

Them: three different ways and how you can apply that to keep your house either warmer or cooler depending on what's going on with the external environment. And, you know, like, in middle school, specific heat capacity

Me: Right.

Them: is not taught. At the middle school level. That's a high school level concept. However, getting the intuition Joel was pointing out, getting an intuition like you know, this material is heating up a lot faster than that material, is super helpful for material choice when designing your house and then when you get to high school and you're like oh so specific heat capacity is what I was observing back in middle school when I did that and your light bulb goes off.

Me: Exactly. No. That's and we see that all the time with the power of these molecular simulations in is that, you know, if you're showing guts and all, it's still the phenomenon still makes sense. I mean, you see the thing absorb and remediate, and you're like, well, I stand next to a wall and I feel the warmth. And you don't need to talk about quantum levels, but if you've seen things sometimes and sometimes not, and then you're you're teeing up, you know, things for five years later. Who knows? Mhmm.

Them: Exactly, yeah. And you're connecting like their real world visceral experience with their own environment with the the simulation that they're playing with, which

Me: Mhmm. Mhmm.

Them: kind of strengthens that learning objective there. And you'll notice, Maaroof, this is different than the know, we had the convective or thermal tran transfer. SIMS as you know, that that's when we get to those next modes instead of, like, starting with that know, the idea was, hey. What's really, like if we actually have the first level, the way that we had our kids look at you know, type one versus type two, and they're just like, a pipe is blocked. And that that's the level of intuition we wanna prove out sort of first and then gradually layer in those other more complex things. So this sort of why the molecular thing here gives us gives us a lot We're able to answer a bunch of questions upfront, like, I think what Leslie is hinting at is, hey. If we rotate a thing by 90 degrees and need to muck around with boundary conditions, then that is not always gonna be a quick, quick modification. And perhaps, perhaps we actually need to adjust a little bit

Me: It's a

Them: our tweaks to just sorta Like, what? Have a summary

Me: it's a back and forth. I mean, we find this too. We'll say, oh, I wish we could do whatever, and then we're like, oh, wait. Yeah. Can we actually reflect easily or not? Do we have to modify? And sometimes we're playing behind the scenes where there's an invisible barrier or something. You know? So it's a it's a back and forth to make any of these serve the pedagogical goal that you really want them to serve without, you know, being not realistic or too realistic.

Them: Yeah.

Me: Yep.

Them: I mean, it's you know, it's it's exactly like

Me: Right.

Them: in biology, you show a cell all the time, a eukaryotic cell all the time. Does it look anything like a real

Me: Mhmm. Right.

Them: eukaryotic cell? Never.

Me: Yes.

Them: It just can't or the complexity of it

Me: Mhmm.

Them: would be impenetrable for

Me: Exact

Them: anybody in a K\-twelve space, much less a college student. Yeah. But I wanna I wanna make clear that there is a a deliberate and and choice distinction between what we show and what we need to encode in the model. Right? The whole reason why it's worthwhile to to build the model with some semblance of physical reality to it is that you can then do lots

Me: Right.

Them: of other things with it that you are going to wanna do. You're gonna want us to put a layer of other stuff smacked up against this layer. You're gonna want us to we are. Yeah. Open this open the window. Right? Open the c know, put the vent in the ceiling, put the vent on the side of it. Right? You're gonna want all those things. And so even if I am not showing you a a separate glyph for every single, you know, thing that is going on here I gave you the the ability to turn them on and off or whatever. And by the way, you know, when we get serious about this, we really need to, like, give you better art. For the various pieces here. Right? All of that. But, you know, but if I don't have that underpinning, then I am back to the place where I'm trying to individually draw, you know, 12 different animations, which is totally not the

Me: Right. Exactly. Yep.

Them: point. Right? And here and here's a suggestion off the top, Leslie, because

Me: Mhmm.

Them: you know, if we look at a versus b, the original versus there, if we could certainly, the question of so I'll just draw. So this is where we are right now. If we go back to the screenshot, I'm just gonna draw on the screen here. Yep. You know, first, just sort of from a visual point of view, if we're starting from a URL that strips away all anything except what's in the rectangle, that that's meaningful even if it's the exact same SIM that is

Me: Right.

Them: other panel. This bit is identical terms of know, compared to the other, other SIM.

Me: Yep.

Them: And then I I guess what I'm curious about is what what were the what were the, like, invisible bits that were in there that were, like, because is there, like, an off the cuff tweet that we can make that just sort of you know, do it. Like, random. You know, Joel, I I appreciate what you're trying to do for me here. I I I truly do one dev to another. But but I think it's a like, I think it's okay. I think we got it under control. Okay. It but it's just, like, not

Me: Yeah.

Them: Yeah. It's sort of like, hey. It actually needed a a little bit more conversation than than Yeah. But it just it's mostly expectation setting. Right? Just just so that you will understand what we are doing when we are when we are doing this. But I think it's alright. I think we will have something meaningful to show you next week. That you can play with and try to embed. And all of that. It's just that from there, there are gonna be an 27 things that you're gonna want and, you know,

Me: Yeah.

Them: we'll all just discuss whether they are worth the time that it takes to to do each of them. But

Me: Yeah. I think I think the finite element model example is a good where somebody's like, oh, can I make that triangle bigger? And you're like, not that triangle. You know? Those other four, all fine. Those other 25, yeah, but yeah. Exactly.

Them: Yep. Yep. Yep. But but so far, I don't you know, I don't think we've hit the limit of our ability.

Me: No. No. There's lots of if anything, we're discovering

Them: And

Me: interesting questions that we want to ask to understand how to, you know, make the next seven variations of this in some interesting way. And we're going to do that, do we need, you know, a different capability or we be setting this first one up in a way that then allows you to add those layers, you know, those kinds of things. Mhmm.

Them: Yeah. I think that I will be interested in talking about that is, like so I said there were two things. Right? So this is sort of one. Two is you know, how much how much of the metering control metering, feedback comparison UI do you want us to take on? Or at least consult on Right? Because there's a completely separate question here about you know, where are the temperature sensors. How do they convey their feedback? How do we let students record that information and compare it? We were talking about the, you know, the testing stuff that I worked on for Massachusetts. I sent you that paper this morning. You know, we could just talk about some of those ideas and philosophies We could try to implement them within these panes Or Yeah. We make sure that we're feeding you back all of the right information so that you guys can do it. You know? Right? Yeah. Yeah. The temperature probe, is worth showing Maaroof what, what I was surprised I read through the paper. Thanks for sending. What I was surprised to see, is that, you know, these approaches being used in actual you know, sort of testing scenario. You know, I never seen a test beyond The US choice style. Which is incredible. Here, I'll just pull up the the PDF. Oh, yeah. I was just looking at some some cool because it this is relevant actually to the the current

Me: Right. Mhmm.

Them: or game design, which is their we're in we're trying to have, like, some seasonal variation, some location variation. Two or three. And that affects your sunlight. Situation.

Me: Mhmm.

Them: So I I really like this just sort of and I was surprised Let me zoom out to see, like, hey. Kids actually attest looks something like this is what I tell me. Mhmm. Right. I got this so they do a sim sort of actually translation to what we're doing. So short answer is like, hey. Yeah. We we'd love help on because this is, like, this has already gone through some testing cycles, so there's something you learned here, some things you do different. But what I like is we could see a through line to, like, actually even standardized testing being even though that's not our focus. Right now. This is what Charlotte and my call, like, the note notebook view. And in that notebook, there are some choices and students indicate those choices. And that gives you a sense of how well do they understand what's going on in the

Me: Mhmm.

Them: in the scenario. So

Me: Yeah. And the the really interesting question in some of these, especially, I think, in this project based, work where everything is open ended is know, how do you, as a teacher, get a sense of where

Them: Yeah. Yeah.

Me: kids are and some kind of formative assessment that still true to the the approach. I think, really, a way to do that. So if they were able to say, alright. Here's a a house. You know, Tell me if this one is effective. You've got two temperature sensors and you've got a, you know, a button. You know, and everybody's got the same one there even though they're all designing different ones you know, on their own. You're in a place where the teacher's got some some sort of touchstone, and you're laying the groundwork for things that might be more standardized to post test even if it's just a post test. Right? Mhmm.

Them: Yeah. So I think we're we're we're gonna wanna inform what we're building. Like, this one has an actual 10 measurement and Mhmm. Make some choices here. And I think, you know, we don't wanna re I think we wanna benefit from the this probably went through a bunch of cycles. Oh, yeah. And I can already see some choices in in the in our three dimension you know, the the three dimensionals of change is one of the things in this panel a. But this is a very mature about how we deal with time, which is kinda tricky in trials. And I love that it's, our six second, eight second Sims, but then snapshots in time It's a very different mindset from where we had even been thinking until I saw this paper just when you sent it. Yeah. Yeah. Time time was fascinating and something that that as you say, matured. Oh, yeah. You know, the first year or two of the project. And you will notice that every well, not every single one because there are a a scant handful like the one immediately above this that are not time based. Right. But Right. Yeah. Right. But most time is dealt with here. Because it it that we want sensors in our sims because we know we have the high ceiling that we can simulate there, and so we we have the opportunity for those. More rich experimentation. And so so definitely definitely and then, you know, here's relevant to Tiny House too. Like, if there's a natural disaster surviving, makes total sense for us to be leveraging you know, this sort of approach. What I'm wondering offhand is this was a cool sort of documentation of, hey. This is some of things we learned and so it's like, how much of this, can we call as validated at scale versus, like, early pilot sort of, like yeah. Is there, like, sort of trying to gauge, like, how much of this can we say is, hey. This is how it's just gonna be going. Like, we look at everyone's assessments, today across all states, like, has this not caught on? Was there like, what I'm saying is, like, the barriers as to

Me: Alright.

Them: you know Joel, yeah. We we I I I have a whole lecture on this. We could talk about it. I'll give you the gist of this later so we don't have to go over it. But this is not where everybody is going to be heading.

Me: Yeah.

Them: For at least the next five years. This this is the NGSS states. And I wouldn't expect that. And so I guess if there's efficacy data to go along with this, that would increase our aggression on saying, hey. Let's actually not reinvent If this was, like, an end of, like, 10,000 students went through you know, a b tested with, like, a p value that we can say, look. This is just a much better way, traditional versus sim based That's what I'm wondering from a data kind of perspective.

Me: Yeah. That's a good question. I don't know that there, I mean, so I think the thing we can say is that the end of students using these kinds of simulations is you know, is large because they were full full state pilots or the work that we're showing there in in those cases. So they were used at scale. Yeah. Now whether

Them: The cast does it, and that's the massive scale.

Me: 25 states will be doing this two years from now

Them: Yeah.

Me: is a different is a different question. Yes. It's, you know, it's complicated. It's hard. People don't always get it. You know, like Charlotte said, some states are more bought in than others. And even if you're bought into NGSS, are you bought into changing your assessment system? Like, there's lots in there. So Mhmm.

Them: But California has changed their assessment system to this. And they have been doing it, since, I believe, 2018\. It was 2017 or 2018\. So you can get massive numbers from that as far as like the efficacy of these tests, how well students are doing on because they do have simulations in their test on the cast. And that's our our biggest, I guess, sample size is over in California for tests like this. There are other states that are doing it as well. Massachusetts I did not know, had started doing this, and apparently, new which is great Massachusetts you know, it's much smaller population than California.

Me: Mhmm.

Them: I I think we would want if there's data mean, essentially, I'm just looking for a randomized controlled trial, a efficacy studies, like Edutopia, and the foundation based lean heavily into, hey. Project based learning, it's better than not doing it. And here's, like, a bunch of of like, here's a bunch of, like, carefully controlled studies to sort of show that. It took a long time. It took a lot of money.

Me: Mhmm.

Them: And, and do have some comparative, you know, outcomes at the randomized control trial level. Is like Yeah. And I think I think the thing to recognize about this particular particular work is that they were trying to test if they could assess the standards that needed to be met, not it's not a teaching it's not a teaching instrument. Right? So it's an assessment instrument. So all you all you really get to know is whether or not you're just as good or better, hopefully better. At assessing, you know, all of the both both the actual standards for science and then the practices that go along with those that are baked in here, graph reading and, you know, controlled design of experiments and all of that other kind of stuff. Right? Can you assess all of that stuff without giving a million multiple choice questions? Right? Right. And and you can even see if you look at this stuff clip with the right lens, you'll even see that we were working around the limitations of Pearson's assessment system which is why they say a, b, c, d trial and it allows them to reference the sim in a way that didn't bust their you know, their general record keeping system. Lots lots and lots of stuff. So, you know, I don't know if you're gonna get the efficacy data that you want here. But I think there is a lot to learn by examining these and thinking about students need to compare things. How do they compare them? How do they generate them? How much manipulation and control do they need over trying things and then discarding them or rerunning them? One of the surprising things and I'm not sure that it's actually stated in this paper. Is that although students recognize that they were in a in a in a high stakes environment and that they had only a limited amount of time to do the test. We found that the average number of runs per SIM was somewhere between twenty and fifty. Right? You've got five slots. So they understood that they were only gonna get the keep a certain number, but they needed to just, like, yets around and yets around and yets around. Oh, okay. I kinda see what you know? Right? Like, I kinda see what's going on here. And you can watch in the data. You can watch them exploring the problem space. And then they go back and and construct a more thoughtful thing, or they don't. Right? And that part that's the part that you need to under you need to see in the data and understand and you know, and then watch what they do after that. To to know if they have kind of got know, what's important about this problem. So right. Like, there's a lot of

Me: Yep.

Them: there's there's stuff there about just how to lay them out and make them accessible. And the kind

Me: That

Them: to watch for. You know?

Me: And I think the efficacy study question I I think the pre question to that to some degree of cells itself, which is to say, if we were designing a randomized controlled trial about assessing students' ability to engage with the practice of NGSS. What would be our control? And you might look at some examples of those where they do it with multiple choice questions.

Them: Yeah.

Me: I think if you laid what Leslie just described next to those, know that you would have to do the study to convince people that there's more richness in option a where students are engaged in the practices.

Them: Hey.

Me: Yeah.

Them: Play devil's advocate if I because I never see anything. When I see that I grow growing up in Jamaica, first of all, I'm just like, wait. You know? If I'm not, like, one to one with students with devices that can deliver this and we're trying to change the standard, If I'm the minister of it, he he's been emailing me from Jamaica.

Me: Okay.

Them: You know? He's like, so can we don't like to deal with the government people, but but they have to make a choice. Hey. Do we invest in

Me: Right.

Them: probably Chromebooks in our system so we can have this better testing system But if it's just as fine as to just multiple choice circle,

Me: Right.

Them: pencil, like, then, you you know, the devil advocate part of me is like, hey. Is this better at a I hear what you're saying about, hey. This wasn't trying to teach. This is, like, a better way to assess in theory because it's actually asked

Me: Mhmm.

Them: measuring more what we care about. Yeah. Mhmm. So, Joel, like, the what you're talking about

Me: Yeah. That's it.

Them: the paper and pencil thing, nails d o k one, and sometimes DOK two. Yeah. And he's fussy with DOK three. Right. So I'll this will take you to DOK three Yeah. Yeah. In theory in theory. That's what I'm trying to ask a date. Well, it it's as far as data, you know, we can dig into it. But there is a lot of data that had been produced by the University of Connecticut, like a lot of states started when NGSS came out, started going, how are we going to assess this? These performance expectations

Me: Alright.

Them: cannot be assessed with your typical star or, you know, for the best kind of style exam. Right. What are we going to do to scale up our assessment so that a computer can still score it but we are actually assessing a DOK\-three level performance expectation. And so they have done massive amounts of research across many NGSS states, but University of Connecticut started it out And then a lot of states like on the West Coast, Washington, Oregon, and California, Gloomed on research and started developing these tests. And took over a decade to develop tests that they were then convinced, yes, our far superior at measuring student performance this deeper level of understanding than your standard your typical standardized, like, fill in the bubble kind of, yeah, test. Yes. I I would need to see that data because this is a very high cognitive load assessment. It requires digital devices, which I've not had personal experience is a a winning strategy unless they're strong like, evidence to say, yeah. This thing's measuring or we're trying to measure it's measuring it better than whatever is our next best thing, which is probably just some things on paper. And, honestly, just doing a good old fashioned project and assessing it is like, that's that was the current best answer that I think we had. Was, hey. Look. Two projects that are like, not, like, multiple choice tests. Like, you know, it's like, build a thing. Do something. It's not a onetime high stakes test. It's like a multi you know, multistage open ended problem but aligned with standards, and that's the PBL story that we've learned It measures what we want, but it's hard to implement at scale, right, is maybe the Yeah. I mean, New York used to do that with their Regency exam exactly what you're describing, and the problem was was expense.

Me: I

Them: And so you couldn't scale that up to larger markets like Texas, Florida, California. Yeah. Yeah. So I'm I'm trying to assess that if know, what I'm seeing on the screen here, how well know, what do we what do we know here about, like, how well this is capturing what what we know works? And if the answer is, hey. Just anecdotally, we have draw some lines and extrapolate and say, hey. It probably is a step up. I could probably the counterargument to these things is that without, like, higher fidelity, for example, that it causes some in a high stakes testing environment that we may just be at a high of a cognitive load or perhaps students have less familiarity with the you know, they they have to do a bunch of abstraction and translation here on this particular thing. This is hard for even me to do. Right? Like, the it takes me a moment. Right? To to to get through what I'm see if I were actually putting myself a kid's shoe on this screen in a way that I don't, you know, I I could hear the counterarguments for, like, hey. There's some danger there that would need to be, included in in another version. I don't know what those are. But if there is probably someone would have measured this. Their psychom if this is Pearson, they put their

Me: Yeah.

Them: this thing through the you know? And maybe that's proprietary because they don't want people to know. You know? So so I guess that's what I'm getting at is, like, woah. Maybe as a follow\-up thing, if there's anything out there that's helpful for us to know how much we wanna be you know, drawing from from this. But I'll assume we'll just use our intuition for now and absence of data, and that that's okay. But if we have data, then we'll we'll want to, not reinvent the wheel if, like, psychometric evaluations have been done, and we're like, oh, you know, like, that was really solidly measured, and then we're just we have a baseline to start kinda measuring where where we're at ultimately with our SIEMs would be something we would want your

Me: Mhmm.

Them: Yeah. Basically, a repeat of that work with the validation part to say, yes. Are they at DOK level three with this, simulation approach? If that makes sense.

Me: Yeah. And I think if you I think if there's a there's probably a

Them: Yeah.

Me: too. I mean, I think if you're starting with what Charlotte's alluding to that, you know, obviously, you know, California, etcetera, Connecticut have have sunk, you know, time and energy into answering the question enough that question enough for themselves that they were willing to, you know, develop tests

Them: Or we're, like,

Me: that were at least a different NIFO, which I think is somewhere in between what we're seeing and and the pencil and paper.

Them: Yeah.

Me: And and you're saying that the lever that you've got within this curriculum to pull to pull is highly project based. Yet we're trying to understand something about it and give teachers a handle in their You know, that formative space in between there, is one that gives you some more room to play too and the the constraints of, you know, requirement for accuracy aren't as high. It gives you the opportunity to say, oh, we are really seeing this. The okay knowledge coming through in a way that we can compare across a class that's useful for teachers. And by the way, we have, you know, models

Them: Yeah.

Me: that can bring this into the assessment world. Know, I think those things lever into one another too. Mhmm.

Them: Yeah. And, ultimately, because when we go talk with George next, he's skeptical about you know, the you know, approach where we, like, sort of aggressive aggressively change the standard at the publisher level. That's a very reasonable strategy for us It's very high high impact, you know, but like, very difficult path. So you know, if we can go in and say, hey. By the way, there's been two decades of research on whatever we call this. This is a better way to test. To test are not testing what we need, and here is, like, the overlap. And we've been thinking simulation for project based learning. But by the way, all the publishers like the Pearson's they're already doing this, and we would love to show them a a a, you know, an advanced view that is making advantage of the AI wave that is definite you could definitely see how this this with a Canmigo style approach plus this becomes potentially even powerful for prac you know, practice before the high stakes thing.

Me: Mhmm.

Them: So the more we're armed with, hey. We're here is here is our confidence level on this. We know this is gonna work for sure because of x, y, and z. And here's our tweaks on top of this, you know, foundation. We kinda need that to be able to get over George's skepticism on you know, whenever there's, like, a crummy system that has lots of room for improvement, there's a temptation. Hey. Let's just build the thing we need from scratch without paying too much attention to all of the Pearson's whatever system they had, ABCD. That's a leftover thing from their previous password. That's maybe that's not a constraint we wanna take on right now.

Me: Mhmm.

Them: That that makes sense why I'm why I'm getting at

Me: Yeah. And it feel it feels like to me the, you know, the sort of

Them: data

Me: thought path might be California is, you know, on its way toward what we're talking about, and they are they're not gonna turn one eighty. They're gonna continue trying to look for something that's the the next better version of what they're they're doing. And that's not happening next year because it's that's gonna take a long time. So if you're using the word assessment in a sentence, you are automatically talking about a ten year time frame already.

Them: Yeah.

Me: So, you know, are we laying the groundwork for the kind of thing that needs to be in the classroom to meet those? And do we have do we have an understanding that there's a path from that to then assessing it? Because the problem is we've got this grand thing that really gets kids moving, and then nobody can fit it into paradigm of, say, assessment and all of a sudden then you you take the air out of the tires to begin with. So I don't think you need to develop this, but you need to know that there's a a path that leads from this curriculum.

Them: Yeah.

Me: The kinds of assessment people are looking for. Mhmm. And I that's plausible and doesn't require you to try to make a deal with Pearson next week about state assessments for 2035\. Mhmm.

Them: Yeah. Yeah. Yeah. That path is clear. That's a huge win for us because it gives us tons of ammunition to go turn around the actual publishers and folks who set these standards on these tests because they're, you know,

Me: Right.

Them: People have been trying, and it's a hard hard thing, but we have a

Me: Exactly. Yeah.

Them: potentially powerful hammer, here. And so so I know we're at time. Maaroof, hopefully, let's give you all a sense of where at both on the current sort of SIM, integration feasibility path as well as well, this was a another thing that came up that, it's exciting because I think I learned a bunch even in a a

Me: Great.

Them: just coming through that paper. Any anything more there, Leslie, I can definitely send it our way. And we're definitely a game to we do wanna be, know, leading into as we build out what we're doing, like, if you have, like, you know, your expertise on sort of fair fair game there in the pathway. We we have this initial thing right now, but yeah, I'd be excited to to keep going down that path.

Me: Cool.

Them: Right. Yeah. I will take a look at it. And I

Me: And we say in thousand emails. Right? Yeah.

Them: once I catch up on budget stuff.

Me: Exactly. Well, it was great. I'm glad this worked out after all. And, Leslie, you've got, you know, some stuff

Them: Alright.

Me: I'm chugging. I'm not gonna speak for you because you're disappearing after a little bit too. Right?

Them: I I have some stuff chugging. Do we have a thing on the calendar next week?

Me: That's a good question.

Them: Yeah. Can we wanna protect some some of the roughly Yeah. Any anytime, like, well, not anytime, but Wednesday through Friday next week. Yeah. When Wednesday, Thursday would be ideal because the long weekend, I'll actually be off on the Fridays.

Me: K.

Them: Like, Thursday, and I'm trying to remember. You guys are in California? At least some of you.

Me: California and Switzerland, so

Them: You can I I I'll happy to join next week? So

Me: this time, okay. Okay. Great.

Them: that you have a full day available, respectively, instead of on an hour So how do you feel about either one or

Me: Excellent.

Them: 02:00 on the twenty eighth? One's good for me.

Me: This eastern. Right?

Them: Mhmm. Yeah. Eastern time, so it would be ten. Your time. Yeah. It's good for me too. Alright. I will co op my one on one time with Scott. Who is the engineer who is working on this project. So that'll be fine.

Me: Perfect. That'll give you guys a chance to to connect

Them: Okay.

Me: And I you can add me as a maybe, but I, you know, fifty fifty fifty depending upon my schedule.

Them: Alright.

Me: Know,

Them: Yep. And then, you know, that way I can connect you with Scott. And as you, you know, have more questions or wanna try different things, you can just work with him directly, I think. At that point while I'm on vacation.

Me: Wonderful.

Them: So Guys, nice to see you again.

Me: Thanks so much. This is great. Mhmm.


