

**Chad \& Leslie with Charlotte \& Joel**
=========================================

Attendees:

lbondaryk@concord.org,charlotte.luongo@glef.org,joel.sadler@glef.org

2025\-08\-18T14:00:00\-04:00

\-\-\-\-

\#\#\# Meeting Overview

\- Chad (Concord) and Leslie Bondaryk (CTO) with Charlotte Luongo and Joel Sadler from George Lucas Educational Foundation (GLEF)

\- Focus: Small integration tests between Concord’s molecular simulations and GLEF’s 3D house design environment

\- Exploring tiny tweaks and URL\-switchable configurations for learning experiments

\#\#\# Solar Heating Simulation Integration

\- Starting with molecular\-level thermal energy transfer simulation

\- Two\-state system: indoor vs outdoor temperature scenarios

\- Window scenario (glass allows solar radiation through, heats interior more)

\- Solid wall scenario (brick absorbs radiation, less interior heating)

\- Visual elements needed:

\- Temperature meters showing comparative indoor/outdoor readings

\- Kinetic energy visualization (molecular movement/color coding)

\- Air molecules inside house showing thermal response

\- Static legend below animation (not toggle\-based controls)

\#\#\# Technical Implementation Approach

\- Concord provides embeddable iframe with two URL configurations

\- Initial scope: rearrangement of existing elements, not new development

\- Temperature readout could feed data back to GLEF environment

\- Not bidirectional control initially

\- Hard\-coded scenarios (hot vs cold states) for first iteration

\- Timeline: One week for basic rearrangement version

\#\#\# Assessment Integration Examples

\- Concord showed Massachusetts state test simulations (5\-year project, \\\~35 interactive assessments)

\- Key design principles from assessment work:

\- Maximum 2\-3 variables for student management

\- Comparative evidence generation (A/B testing approach)

\- Pictorial data representation for accessibility

\- 5\-minute interaction windows for high\-stakes testing

\- Pearson collaboration included psychometric validation and correlation studies

\#\#\# Technical Constraints and Considerations

\- Chromebook compatibility challenges:

\- Texture resolution and download size limitations

\- Inconsistent 3D rendering across OS/browser combinations

\- Current molecular simulations have JSON configuration but fragile parameter space

\- Stochastic nature of molecular models requires careful tuning

\- Game engine approach (Unreal) hits bandwidth/hardware ceiling on standard Chromebooks

\#\#\# Broader Vision and Strategy

\- GLEF experimenting with YouTube\-style streaming for high\-fidelity simulations

\- Hybrid model: Basic Chromebook compatibility \+ optional high\-fidelity mode

\- Potential for stealth assessment within project\-based learning environments

\- Interest in Pearson\-style assessment market if integration proves successful

\#\#\# Next Steps

\- Concord to deliver rearranged simulation with two URL states by end of week

\- Integration testing with GLEF’s 3D environment next week

\- Target: Demo ready for September 8th GLEF meeting

\- Leslie Bondaryk available this week for handover/coordination before her time off

\-\-\-

Chat with meeting transcript: \[https://notes.granola.ai/d/0b90cd76\-91ca\-4f72\-a35f\-30320094df70?source\=zapier](https://notes.granola.ai/d/0b90cd76\-91ca\-4f72\-a35f\-30320094df70?source\=zapier)

\=\=\=\=\=\=\=\=

\-\-\-\-

Granola link: https://notes.granola.ai/d/0b90cd76\-91ca\-4f72\-a35f\-30320094df70

\=\=\=\=\=\=\=\=

Transcript:

Me: Hello?

Them: Hey, Hello.

Me: Hello.

Them: How are you all today?

Me: Doing well. How are you?

Them: Good. Good. Enjoying summer still.

Me: Yes. You and me both. Just joined the enjoy it as long as it still lasts, which is not ever as long as it should. It feels like

Them: Yeah. I can tell you live like in the northern part of the country just from that statement.

Me: Yes. No question.

Them: Yes. And today is beautiful. Today. Where are you located? And don't say Concord. Charlotte: Near Boston. There we go. Yeah. Yeah. Near Boston. Is this Will from Alpha folks? Are they in that vicinity? No. Those guys are in Illinois.

Me: I mean, Steven Wolfram is in that vicinity, but that doesn't mean he ever sees anybody or really exists on anybody's radar screen. He's supposedly in lives in Concord, but that's all I know.

Them: Yeah. Yeah. So I've heard.

Me: Mhmm. Mhmm.

Them: Yes. My husband actually wound up sitting next to him on a plane once. They had a very interesting four hour long conversation.

Me: I bet.

Them: And then never spoke again. Yeah. I've been following his, you know, his Mathematica stuff was always sort of a partial interest and relevant to our simulation stuff because it in some ways, kids should be having notebooks, like a modern Jupyter notebook mindset that I think has now supplanted that

Me: Mhmm.

Them: that model. Yeah. So it's always been so I've been a fan of what he did there, and I can see you know, the modern Jupyter notebook type things being a lot of what he was hoping for. And then I'm sure he's bummed about some things and

Me: Right. Probably.

Them: Right. Right. With the nail visualization is pretty nicely. You know?

Me: Mhmm.

Them: Mathematica. And the paywall was always my issue with their approach. Mhmm. Just yeah, just the multi just the the big barrier to actual students getting in there and doing you know, creating their ideas.

Me: Mhmm.

Them: Yep. Yep. Alright. I think we don't have all that much time today, so I wanna make sure that we get to the things that we need to get to. So, again, I'm I'm going at this from the premise that we are still talking about like, tiny tiny tweaks to things that you can insert in your stuff, maybe with a few URL switches on them. And then learning from these things what what we need to do in in the larger. Yeah. Exactly. Yeah. And this one, you know, we, of course, have a longer list of things. But this was, like, you know, sort of, like, the simplest, like, yeah, that's just definitely a rearrangement of an existing element Mhmm. Mhmm. Impact this right away. That's We have a meter we have a meter. We have a legend. And we have a thing that you can bring up in two two states, I think. Which I guess we would, you know, set it up so you could put it in one of two states about what temperature and how much solar radiation was hitting a thing. Right? Mhmm. Mhmm. So just to just to show you how how the whisper down the lane thing goes, I looked at this and and and had a little moment because I thought you wanted the whole thing. Oh, like, I thought you wanted us to make this part too, which Oh, we can.

Me: I was like, I don't think that.

Them: Right? And then, like, what did I wanted to pull up a thing to show you No. Like, we totally can make things like this and have made things like this. Nice. Like, you know, and there's lots to talk about. Like, we should talk about this thing that we've done we learned some things about allowing students to collect data in, you know, in different runs and and setting setting variables and so on. Right? This this was made to go on a state test. Mhmm. And we have also made version of this where we have embedded There's a there's a larger sim with some animation that that goes along with it and then have embedded, like, the micro version. Right? Like so we we've we've done things like this, and I kind of originally thought that that was what was being asked here. Chad talked me down off a limb. I should have been clear that

Me: I'm like, that's fine. I know. So I saw the red rectangle, and I had been trying to to think about how one might do

Them: yeah, your sim no. Yeah.

Me: before independently. So okay. Good. Mhmm.

Them: Like, embeddable in an iframe.

Me: Mhmm.

Them: In the larger environment. Right. So this this piece. No. Yes. Right. So The human body stuff you were seeing was all it's actually all unreal. Engine running on an iPad and but then everything that's UI is just web You know, it's just pulling in from a URL. Mhmm. So we mix and match you know, resources all over. And and so we need to reinvent the wheel on the you know, whether it's lighting or physics. You know, we have sort of, like, a default starting point on the in the three d world. Sure. Yeah. Absolutely. So if we're just talking about this and we're not talking about, like, trying to rerender it or change the animation or like that, then I think that's fine. I guess I just need to know if, like, you genuinely only want to Like, what what's going on here?

Me: We should clarify those. Are those is the intent there the two settings for that when the indoor and outdoor rectangles are there? What's the what's the thinking right now on the is that is that have relation to the iframe configuration and the and settings for temperature?

Them: So right now, what the thinking was is I know you don't for this particular simulation, you don't have exact

Me: Yeah.

Them: temperatures. It's more of a range. Like, is it hotter? Is it colder? Is it heating up? Is it cooling down? And so the idea currently, like, maybe as we go down the road, we would add the ability to have exact temperatures there. But right now, the idea is, like,

Me: Sure.

Them: to keep it relative in the sim. So kids can be designing out their house, and we would be setting up the rules in unreal of like once you get an enclosed space, if are they using this material or this to to calculate their indoor versus outdoor temperature the main sim. Now if they want to go why? The power of your simulation here is like, well, why is is this wall causing this type of material, maybe a solid material, causing less thermal energy transfer through radiation from the sun, than a window and then they can see molecularly what's happening is this material is absorbing solar radiation, and then it gives off some infrared, yes, if we change that material, for example, to glass, then they would be able to see the solar radiation getting through and that helps explain why if you put a big glass wall facing the sun, house is going to heat up. But if you put a big brick wall, house may heat up, but to a much less degree because it's only getting that infrared radiation from the wall. I see. So the thing that really needs to change here is the material. Yeah. Yeah. Yeah. Right. And then we need to have meters on either side so that you know that in in one case, it's hot outside, but not quite so hot inside. And the other case, it's hot outside and maybe even hotter inside. Yeah. Very comparative. Like, you know, yeah, what's going on with how hot is it inside versus outside, and it doesn't have to be exact, it just has to get a gist of this setup is gonna create a hotter environment here. Versus here. And this particular sim happens to have you know, indication of air molecules on this side. Do we wanna hang on to that, or is that just getting in the way?

Me: And it seems like those were added, right, by when in your envision there because I think the other one has it Well, I guess it does happen vertically. Yeah.

Them: So the reason why I

Me: Yeah.

Them: I kind of like to keep them on the inside is because we do need students thinking about what's heating the actual air in inside the house. Mhmm. And if we're we're concentrating to

Me: Yep. Yep.

Them: start with on solar radiation, And so if you want to know like, okay, well, here's your wall, and you see the wall getting hot. Like we've got a brick wall and it's getting hot because it's being heated by the sun. Especially on the surface layer. On the internal layer, it's not getting as hot, but it is especially, you know, through we're not just looking at radiation when it's the inside of the wall, you're also gonna be looking at conduction, but we don't need to go to that. And then how is the air inside the house being heated by that wall that's being heated by the sun? That's why the air molecules there are helpful because you can see, okay, they're getting a little warmer,

Me: Yep.

Them: but not as much as if you've got something that's completely transmitting all of the solar radiation like a window would.

Me: Mhmm. Yep.

Them: Right.

Me: Yeah. And I do see as I'm looking at the original model that one of the the versions has got c o two and ground. So we do have we do have that,

Them: Yeah.

Me: that sort of heating from the radiative radiated energy.

Them: And the difference here is, like, the molecules that are currently shown in the current SEM represent carbon

Me: Sure.

Them: carbon dioxide totally.

Me: Whatever. But

Them: But here, it'd just be atmospheric gases and, like, every yeah. Yeah.

Me: That's that's fine. Yeah. We can label them whatever we want. Right?

Them: Right. And we're not

Me: Mhmm.

Them: we're not dealing at all with the fact that there is, in fact, error on both sides of the wall.

Me: Yeah.

Them: We're gonna ignore the outside. We're just ignoring that part.

Me: Exactly.

Them: Yeah. I again,

Me: Yeah.

Them: precision is key for me. Right? Like, I wanna make sure that I give you the stuff you want.

Me: Mhmm.

Them: And don't give you the stuff you don't want. Okay. So we do want these molecules inside. We need to show that they are different I guess I guess it's true that they're smaller. I don't really know if they're small.

Me: Yeah. We can change that species.

Them: But but we can pretend, but they do need to move

Me: Yeah.

Them: they're heating. Like, we need to show the the air heating up. And so but we don't need two different kinds of, like,

Me: Probably not.

Them: same color maybe?

Me: Yeah. I mean, so the one question I have when I'm looking at the original

Them: For the

Me: simulation, it's got a sort of toggle that goes between, you know, color molecules and showing the kinetic energy as a color frame. Did you have a thought there about one versus the other versus a toggle, Charlotte?

Them: So explain that again. Say that again.

Me: On the original simulation, there's sort of a toggle between just showing the molecules themselves with a little highlight if they're activated versus one that toggles to the what we're seeing here, which is a sort of kinetic energy color

Them: Oh,

Me: color ways. So

Them: always yeah. I would say we don't need that toggle. Let's

Me: okay. But and you want the kinetic energy is what you want.

Them: the reason we're showing molecules exactly. Yeah. So we want that we want the kinetic energy,

Me: K. Right.

Them: we also are trying to get them to understand, like, the more kinetic energy it has, it's actually like in this case, it's thermal energy.

Me: Exactly.

Them: So it's hotter. Yeah.

Me: Basically, leave leave that toggle on the whole time.

Them: Mhmm.

Me: Don't worry about the different species and molecules because that's not the point. Mhmm.

Them: Because that's not the point. Yeah. I'm just trying to get a nope. That didn't work out the way I wanted it to. Yeah. The Google Sheet He's trying to get the the Yeah. I'm just trying to make it bigger. There we go. Okay. So this is very hard to read. I'm assuming you would like us to Joel and I were talking about this. We need to for now, don't worry about the labeling. I think we're talking about moving all the labeling to be beneath Okay. The the animation so that, like, our temperature gauge is actually a readout that's gonna change, but our key, like, we've got a color key that says this molecule, if it's red, has a high amount of thermal dash kinetic energy. And then if it's low, it's, you know, quite And that's gonna apply to both the gas molecules and the wall molecules So that's a legend. As opposed to a readout. And then we remove the photons dash

Me: Yeah.

Them: solar dash infrared also to be below so that all of our legend is at the bottom altogether, but positioned in part of the animation that it applies to.

Me: Right. And then they're both static static graphics legends.

Them: Okay. So so we don't need it. Yeah. Do you need do you need, like, pings? Do you need us to give you these? Oh, PNGs for oh, for the legend. Uh\-huh. Yeah. I think we probably you mean in order to Yeah. Just so you so yours match. Like, match this crazy little shit. Yeah. I guess those are dynamically drawn. Right? And Right.

Me: No.

Them: Well, I don't know, but I'm gonna guess that they're that they're just a a GIF.

Me: They look like they're moving and not animated within themselves. It looks like they're a GIF for a PNG Mhmm. That floats across the screen.

Them: Yeah. So I can I can Sure? Dig that out of the code and and

Me: Mhmm.

Them: give you that separately so you can use it. Yeah. They don't squiggle around at all. They yeah.

Me: Yep.

Them: Okay. No. You know, again, I mean, this was done kind of a while ago if we were to do this today. Or maybe if you want us to in the future, we can, like, we can do a better job on that. Kind of thing. But alright. So what about like, temperature in this case, I think refers to temperature of this wall of molecules. So no, I think we want that to refer to the air temperature inside the house. Because the challenge for them is not how hot does your external wall get, but can you use passive solar heating to make the inside of your house more comfortable? So it's like an energy efficiency challenge, like Or can you keep the house in a very warm environment cooler simply by considering window placement or the type of wall that you're using. So it's that it's ambient indoor temperature is what that should be showing us.

Me: Okay.

Them: Right. Alongside there. The temperature of this space?

Me: Yeah.

Them: Yes.

Me: Mhmm.

Them: Fine. And are we doing that, or are you moving that meter outside? Like, do I have to communicate a value to you as an output?

Me: The original one has a temperature within it.

Them: Sure.

Me: But

Them: Mhmm.

Me: it's a the the one question I'd have is it it it it it can be high it can be much more stochastic if the number of molecules is smaller, obviously. In this case, it looks like the behavior is relatively smooth. And with those air molecules. We'd have to play with that if we were providing that temperature as part of this thing. Mhmm. I think I I I think you could probably hook it up to those. Don't know.

Them: Yeah. I think to start with I mean, eventually, we do want that. We want bidirectional communication eventually on the key key state. But to start with, it's fine if we just have two entirely differently configured JSONs that you know, we've selected a wall here. It's a particular scenario, and we could we could do it sort of the quick and dirty way because it's gives us this answer of, like, how does it feel alongside the three d? There's probably some technical just look and feel sort of integration questions. So we'll we'll learn something even without that communication where we just sort of have a hard coded This is the mode where it's kinda cold inside. This is the mode where it's hot. Hot versus cold. So that's a the window scenario versus non window scenario is what we've been testing on paper with Right. Some scoring mechanics. Right. So those panels are not pictured here, but there's two types of panels. Either it has a window or it doesn't. And so our theory is, hey. If we started off our scaffolding, you know, eventually, you know, we could progress to lots of different material types and the other you know, kind of seductive. Yeah. Well, we're just starting with a. You know, this was, like, level one with, like, the sort of first types of intuitions we wanna build. So, yeah, we we don't need to communicate for, like, that first level. But, you know, if it's if it's a freebie or a super low hanging fruit, then, you know, that would be on if if you know of that to be the case, it's just that would be where we're going to wanna go towards. I don't think it's a terrible idea for us to re to experiment early on with returning a value to you that you can then use. But if you want us to leave, I'm mostly concerned with what am I leaving in this frame. Right? I'm removing this. I'm removing this. Because you guys are handling the, you know, the key. But I can leave this thermometer in here and I can make sure that it is measuring, you know, what we believe to be the the representation of the temperature of this space. I can also return that value to you but you don't have to necessarily draw it or do anything other than maybe just display a number underneath. I guess that's a technical question. I saw with one of the links you sent, it was going through something. Don't forget what it's called. Have to pull up going through something inter lab interactive browser that was just

Me: Mhmm.

Them: you know, sort of putting it in a mode where I could see all the different JSON

Me: Yep.

Them: Mhmm. Files. I messed around a little bit with that is are these sims set up so that if you just hit on a frame reading the JSON every loop? And then, like, if we were to up some internal if we had access to the that JSON file, is it set of for dynamically reading from that on each tick? Or not dynamic in that way? It depends on which SIM talking about, and it and it's vintage, and I don't know that answer for this particular one. Right? Yeah. Like like, again, there's

Me: Right.

Them: nothing about what you just said sounds insane to me. I'm sure we could make it do that. It's just a question of whether you wanna spend the time and money to do it right now.

Me: Yeah. It doesn't doesn't have a a very high highly codified API, it's something that's telling the temperature bar to go up or down. So there's something in JavaScript similar. But

Them: Yeah. Right. But, you know, like,

Me: Mhmm.

Them: just saying, okay. Now set the temperature down here and show me what that looks like. Which I can totally see you wanting to do. I don't I would be surprised if this SIM was set up to, like, actually by directionally to it. Right? It's just a it's

Me: Yeah.

Them: just a a read out of a model that is moving forward in time. Right?

Me: Yep.

Them: And what you're asking is to, like, reset its state. I don't I don't typically have that kind of control. Yeah. Yeah. Yeah. So so I yeah. I wouldn't say as a I don't think we need the stuff exposed to Starwood because I think it just the important thing is actually just starting to mesh these worlds together. The but yeah. Probably moving towards URL parameters and ways. You know, I I think it's just sniffing out if there's, like, problems with and, you know, there may be certain vintages that it's easier or harder.

Me: Mhmm. Yeah. Yeah. And they and they become nuanced. Know, for example, I don't know if the temperature is

Them: Yes.

Me: the overall temperature, if it's easy to say temperature of two of those seven molecules, does that really have meaning or not? You know, so some those we tease out as we went along. Right? I mean, all that matters for the demo probably is that the temperature goes

Them: Right.

Me: You know? Okay. Fine.

Them: Right. And kind of the speed at which it's going up.

Me: Yeah. Right. Yeah. Exactly. Yeah. Yeah.

Them: Yeah. Right. And and and now you get into, like, the reasons why, you know, when we did things like this, we cheated quite a lot. Because we wanted the student to see a particular thing And so there's is it real and is it true? Right? Right. Right. It's a model. It's a model. Yeah.

Me: Yeah. Exactly. Yeah. Yeah.

Them: Yeah. So what are we looking at here with the Oh. Context with because I don't think we're seeing this style. No. And you wouldn't because, again, these are these are all part of a the Massachusetts state exams. Mhmm. So I literally can't expose these without compromising their tests. Mhmm. So I don't just slap these up on my website. But I can show them to you, particularly since I don't think either of you have children in the state of Massachusetts. It's a you're you're okay, but don't take screenshot. The the a so, like, the experience here would be, like, is there data that, like, are these, like, sort of like, tests that people are sort of with some Right. Right. What we're what we're looking at here is using solar power to basically distill water so that it becomes drinkable, and there's a whole, you know, surrounding piece of text and, you know, leading questions that that that lead you up to this. You know, just start with this. But then, you know, you you have a couple of parameters that you can change and say, okay. So what if I start with a lot of water? And what if it's a super sunny day? And I I know some things that I can measure up front, and then I run the simulation. And it is doing two different synchronized things here. One is showing you that because there's lots of solar energy, there's lots of, like, bouncing around and stuff in here, And then what's going on is that a certain volume of the water is gonna evaporate and wind up in the container but free of its salt. And, you know, we can we can compare what happened there with what happened when I had a low volume of happened when I had a medium volume. So while they're being tested, they would run this This simulation. Scenario and then respond

Me: That's the so those are trials. A, b, and c are different.

Them: right? Right. Right. And and, you know, the way this one in particular, when this is for fifth graders. Right? So you'll see that we're not putting a just a data table on here because the standards say that they don't have to know how to read a data table. Right? So we had to come up with a pictorial you know, way to to do these kinds of things. There's lots of for accessibility reasons, 's lots of redundancy with, you know, pictures, graphs, text, you know, and so on and so forth. But the real point is that this this animation here where we show kind of what happens with the water and the and the sun and so on. Right? And then, of course, you you have a really cloudy day, you know, things don't move around nearly so much that there's less bounce here, and there's much less evaporation that drops are smaller and so on. But this is really just an animation. Mhmm. Like, at some point, we said, no. It's really not worth taking a lot of time to encode the various equations. For exactly how fast this water would evaporate, You know, it's really hard in a space of just a couple of seconds to make eight hours of calculation time go by. Yeah. So You've got a lot of, like, very limited variables so that you can Exactly. Yeah. Exactly. Exactly. Right? And even that a big discussion. Right? When when we first started designing the sim, I think they had, five or six different things that the kids could change. We discovered that that was never you know, in a five minute space of time on a test, that kind of thing was never gonna work out. But you know? So there are some lessons to be learned but the primary thing at the moment is just that it is certainly possible to synchronize and composite what is a legitimate you know, atomic sim about how particles move and bounce off each other. Right? This is all using the same the same libraries that are driving the stuff that you're looking at. And just basically timing it such that it goes with what's happening over here. But there's like, two entirely different sets of you know, of timing and and math. And the initial thing you showed us with the shadow type things that that might be. It's it's another right. It's another one of these, you know, we have a three d model now. Right? And and we just we know we know when it's hit certain frames. And we've encoded you know, what the Mhmm. What the behaviors are gonna be. Right? So at this point, That's an animated, shadow. Right. Right. You know? And and it's done with the three d model because that was the right thing to do for this particular but we have some that are actually we have components that grow and shrink. Right? You know, we're as clever as we can be about this kind of stuff. Lightly random question.

Me: No.

Them: Have y'all done work for Ohio? Because Ohio, no. Interesting. Okay. Because this looks a lot like some of Ohio's latest not exactly, but the same level of interactivity and animation.

Me: That's great. Yeah. Conversion evolution in this one. That's

Them: So, yeah, again, How was the response? What's interesting is I guess, from a user this is live in Massachusetts for some assessments or Yep. How is it sort of gone? Is there kind of because I guess what I'm getting at, if there's, like, information that we sort of know is a useful assessment that might inform a little bit of our you you know, we should probably send you the paper

Me: Yeah.

Them: Mhmm. And to That would that would be helpful to know just because it gives us some sense of, hey. I've never seen an assessment like this. Alright. This is a Right. Pretty Joel, I sent you screen I I should have been clearer. I sent do you remember when I sent you some screenshots of some Californian assessments? Yeah. Not not quite as good as this, but they do allow students to do interactive experiments as well for the cast. For I see. That's what you're referring to with with cast. Yeah. Because I didn't Yeah. Yeah. Those must be newer you know, those were They are. They're very new.

Me: Yeah. And these were new in Massachusetts. This was getting to pilot stage at at this point, I think, but I'm not I think they may have rolled it out now.

Them: Because sign up is helpful for us to know what if it's rigorous you know, if it's enough that it was using assessment, that tells us it's sort of, like, not necessarily bulletproof, but it, like, is a useful and there's data to sort of know, hey. It's

Me: Mhmm.

Them: testing for the thing that was on the standard if it went. Yes. Right. And there's a there's a combination. I mean, this is a long conversation, honestly. You know, we we worked on this project for about five years, so we learned a lot of things along the way. But you know, there's there's sort of this combination of allowing space to explore and then ensuring that there's sort of, you will notice that both of these things that I'm showing you, and we made don't know, I think 35 of them over the course of the project, have only two. And in the eighth grade levels, only three. Comparative features because the kids literally couldn't like, manage the variable space. Yeah. Yeah. They more than that. But this is also intended to be for generating evidence, which you know, they can then say, hey. Look. If you compare the evidence that I generated in slot a and slot b, you know, it proves my point, and then they would give them an open response thing where they get to explain, right, what what their thinking is. You know, they needed to do all that fairly quickly because there are lots of questions on a test. So I would imagine yours could have much more elaborate domains and elaborate spaces. But I would still scaffold them this way. Right? Like and I think you are. Right? Like, I think you learned this kind of thing when you were doing the the human body one. Yeah. You know, the first comparison has to show you how to do a comparison. Then when you come back, then there are more things that you can you can dig into. Right? But but we'll, yeah, we'll we'll send you the the paper that we presented The Oh, yeah. That'd be great. Assessment conference last year about this. I'm assuming you worked with, like,

Me: Yep.

Them: Pearson. Oh oh, okay. If you worked with Pearson, then you definitely had access to their, like, psychometric ians. Yes. We did. Excellent. Okay. Yep. Yep.

Me: Yep. Mhmm. Hence hence, the longer conversation than the five years of yes. Doesn't all have

Them: Yes. That sounds that yeah. That sounds right.

Me: right away. Like, this'd be great. They're like, yeah. That'd be great. How about we dial it down seven notches? We're like, alright.

Them: Yeah. Sarah Sarah Crescent.

Me: Fine. Yeah.

Them: Psychometrician I worked with there, and she she was one of the coauthors on this paper when there has, like, multiple sections. One where Oh, fantastic. Okay. Go on about what kinds of things. Is it is it reasonable to try and surface inside of an assessment? And then she talks about, you know, how they were able correlate it with the larger suite of data, what kinds of things they were able to learn. And

Me: And to your point, Joel, mean, all of it, I think, is also giving signals that this kind of, you know, notion that you can do something interactive on assessment, you know, is paving the way. For people to expect I mean, it's raising the bar for expectation of what kids should be doing in classroom. And, obviously, you're doing more in the classroom than you are in assessments. And if you see things like that in assessment as a teacher, you're looking around going, wait a minute. What am I doing preparing my to prepare my students? You know? Shouldn't they be doing more of this in the class? So that's the the hope. Right? Mhmm.

Them: Yeah. That's incredible. I I mean, in some sense, if this is a direct assume this is not every state doing assessments like this.

Me: No.

Them: It's sort of Okay. NGSS align states still, like, you saw Texas compared to this. It's very different assessment wise.

Me: Yeah. It's still

Them: I see.

Me: cutting edge, but, hopefully, will move.

Them: And, you know, so here, just for for the sake of argument is a comparison. About a thing that you can do when you're for doing it formatively inside the classroom. Right? And there's lots well, not lots, but as opposed to five minutes, now there's forty five minutes worth of time. Right? I see a very different You know? So there's it's just more. Right? There's just more and this was built to go with the FOSS program. Right? You know, the the kid has the opportunity to to to go, oh, yeah. There's actually depth to this model. And you know, different things might happen in different cases. And but, you know, we still have to find ways to gather that data and represent it you know, and and and give ourselves tools to think about it and compare it.

Me: Yeah. And so some of those paradigms of

Them: That's fine. Thank you.

Me: how do you feasibly track what happened in a memorable way, how do you revisit states from, you know, from trials, things like that? I think are highly, you know, portable to this kind of a curricular approach where it can be even more

Them: You know? And you're talking about,

Me: Right?

Them: whether or not it's possible to set, you know, the state here. That was a requirement. Right? And so we needed to be able to go backwards and forwards in time, and we save of the relevant information that allows us to do that in both of these cases. This one, I think. I like how you're measuring time by number of storms. Mhmm. Yeah. Right. A perfect example of the kind of thing that, you know, is is is the subject of many hours of conversations. Right? Because this is geologic time. This stuff an hour. It happens over years. And you know, and then but yet, if you're a fifth grader, does the concept of twenty years really mean anything to you? You know? Much less twenty thousand.

Me: I Yeah.

Them: Yeah. Yeah.

Me: Exactly.

Them: These challenges, do they get sort of documented in an open way that is, like, hey. Here's how you know, in some level of this ongoing assessment, like, some of it needs to be hidden. So, you know, distort the actual you know, assessment. But then there's often a piece that's like, well, here is, like, a version of this, the practice problems, or here was a rationale behind the design. What I like about what you showed on the other tab, I mean, there's some very clear accessibility things that play here. And so, like, we're gonna have to deal with them eventually. So that's why I'm kinda getting at, oh,

Me: Right.

Them: what was the design rationale here for this particular layout? Was that codified assume, in the paper you're referencing? No. We we do reference it. We do. Absolutely talk talk about this, and it was, you know, the the fact that these look alike. And so do all of the other you know, 35 that we made, was because we spent a lot of time upfront thinking about you know, how do I build a comparison tool that is easily you know, easily absorbed by a student in a high stress, high stake situation? Without causing too much math anxiety, without causing too much, you know, friction. And so we we worked early upfront to develop these rules. But I'm also happy to have you, you know, have an in\-depth conversation with our, you know, our UX guy who came up with all of this stuff. So Yeah. Yeah. No. This is this is super fascinating. I mean, like, you know, there's a we have chatted with people at Pearson. Mhmm. Not aggressively recently. What There's just a world for what we're doing if it works really well.

Me: And

Them: You know. That yeah. All the assessments should maybe benefit from this hard work and then maybe revamped with some of the degrees of freedom that you get with a game engine that basically you don't have to animate all this stuff by hand. If it needs to be expanded, it's sort of, like, anything to do with lighting and physics and these kinds of things are you know, there could be more participation on the teacher side, like customizing and doing things. Classroom and so on. That's the the vision we're sort of seeing. So we haven't been thinking hard about the assessment piece because we want more of a PBL you know, multi week type style towards a design challenge. Mhmm. We've been kinda trying to figure out ways that we can do some stealth assessments since, you know, the idea is as this would be a long term activity to be giving teachers indications of, like, how well the student's doing, what struggling, that kind of thing without causing the student to feel like every time they are

Me: Right.

Them: interacting with the simulation they are being judged. Yeah.

Me: Mhmm. Yeah. No. I think that's exactly right. And and, you know, I think

Them: Yeah.

Me: to to both of your points, you know, I think on the the point you're making, Joel, you know, I think if there are patterns, you know, examples, sort of design patterns you know, scenarios that you put in front of students that are formative in nature but provide the handles for that kind of more formalized assessment, your able to show them to people who do that or you're able to put them in a a world there and not have it be such a disjunct. You know? And I think

Them: No.

Me: point, Charlotte, the that design of scenarios that are formative but still open ended is something that we've we've worked within a variety of projects where we've sort of had to say, okay. It's often as much about the design of the sort of affordances in scenario that makes it still open ended but all of a sudden, the the way that you have to tackle it requires you to divulge information about your state of thinking in such a way that you would thinking about one in genetics where we had you know, we recognize that if we made eggs that hatched, that then you had to make presumptions about what was inside the egg And as a result, then you were showing us what you thought. You know, as opposed to if we didn't, then we you know, other times, show you the changes right away. And so there are ways that you can sort think through the design in a way that still feels playful and open ended. But occasionally puts you in a formative assessment state. You know, more than others.

Them: Yeah. For sure. Yeah. And, you know, just for comparison's sake, so the the FOS companions that we did. Assuming know about this curriculum. Been around for a while. But, these actually had to span a number of grade levels. So this one's for second grade. So, you you know, you can see we got much cuter, larger, you know, easier to understand. We still wanted these kids to have the fundamental experience, which is you know, recording and generating evidence. And the ability to compare it. Right? You know? I'll do lettuce because lettuce is hilarious. I actually did this because we didn't know what lettuce would look like when you froze it and then unfroze it. And it looks Michael did a beautiful job. It looks like that. It's gross. Right? But you know, now I can compare this with one and right. And decide Yeah. Meaningful comparison. And, you know, when we we take these little opportunities, right, to say, hey. Did you think about this? Right? Like, this lesson is about whether this change is reversible. Oh, yeah. Yeah. It's causing that. And it's not scored or anything, but it's just this moment of reflection in a in an environment where you have the capacity to think meaningfully about these kinds of questions. Right? Mhmm. Right? And then, again, right, like so, you know, we made this this framework, and then we built a bunch of you know, a bunch of sims. On top of it, including a little animation engine because, of course, if we had to act do each of these animations from scratch, we would lose our minds. So alright. But but back to this. All of this is to say, you know, we have used we have done ourselves what you are trying to do here. Which is to use this kind of, you know, core molecular stuff as part of a larger macro view suite and, you know, have developed ways of thinking about synchronizing the pieces and so on. But but what I generally find is that you very run out of headroom without doing something special here. So in the meantime, I'm absolutely happy to leave this temperature meter in here. It's just a meter. It's not a control. I am happy to feed that data value back out to you if you wanna practice Yeah. Like, just displaying it. Yeah. And maybe that's as far as we go with this one. So is there another this was the only one Oh, yeah. I think the idea was to just have a concrete focal point. I mean, there's long list of other things we could on the wish list. But I think the idea is just getting our feet wet with

Me: With

Them: some integration.

Me: with this specific simulation simulation for now?

Them: Right. Okay. Yeah. We want the the solar energy six solar heating of house draft. And just so you can kind of, like I think this this will help you kind of wrap your head around why we chose to go with this obviously, like, less interactive one is we we thought that starting with the molecular view is so important for students to understand what's happening with radiation. That's why we wanted to start here. And it's not that we're not interested in eventually using that 6D view, that is fabulous, but that doesn't show us molecularly Right. Why solar radiation is gonna heat a wall going to heat a house. It's going to, you know, move through a window, that kind of thing.

Me: Makes a ton of sense.

Them: Mhmm. Mhmm. Yeah. In terms of, edit here or or next steps because because I the lab, the interactive sort of browser, you know, I put I like that I could download the you know, hit a button and download offline. So, actually, you know, just took a look, and that runs beautifully, actually.

Me: Right.

Them: That actually would allow us to test way easier because we can just pop that code right into our you know, our prototyping. So what how would you suggest to run a integration test I'm assuming that the things you showed us here yeah, we quickly run out of headroom in these in this vintage is, I guess, what we would expect. So there's some other vintage that actually has the kinds of characters that we're talking about, like, a lot of all of these have some molecular component eventually with some animation component eventually. So you you may know, like, hey. Actually, not this vintage. This other one's sort of better would be open to that. Maybe after we just test drive. I mean, I I think this is a I think this is a fine place to start and if it helps you to, like, feel whether this one's right or the other one's right or both of them and maybe another thing that we don't really even have you know, an example of, right, that we would just build for you from scratch. That's all fine. You know? Whenever when you get two projects like this Mhmm. We tend to build you know, I mean, again, these are for pay work. Right? So we Oh, okay.

Me: The Your your your your policy on your screen, but, yeah, we know you're showing the assessments. Mhmm.

Them: Yeah. When when you get into the yeah. When you get into these, you know, you're talking about you're talking about for pay work. And so we build a you know, a little Yeah. Yeah. Module that that has all of the right features whatever project we're working on. I mean, I guess I would kind of hope that we would do the same for you. Right? And you can see here you know, I'm I'm looking at very different kinds of sims here that are all sitting on what we consider to be the same underpinning. That gives us enough flexibility that we can make the controls look like we want. But you know, many or most of them have a table because that was important. And so we built a table component that we would always be able to reuse, and we built you know, animation controls that we would always be able to reuse and so on. So I guess I hoped that we would eventually be able to build a thing like this for you, and we'd probably present it to you much like this. Right? We build a little internal demo site that was yours alone. You know, that we would log into and you would log into. And when you were done, you do exactly what we did for the FOS team here. Give you a ZIP file. You can see that we actually because of the way their software was set up, we had to build separate Spanish and and and English compiled versions. But, you know, then they could download it and do what they needed to, the code to integrate it into their into their stuff. Yeah. I know we're we're over time, but, strategically, what we're experimenting with is we just plop in a game engine down so we have no ceiling there on one Huawei. Need to simulate And at scale, that's a open technical challenge about how one could get that

Me: Sir,

Them: in a

Me: Yeah. Fine.

Them: classroom scale. Streaming in YouTube style is, you know, the current best guess. We're having a conversation with YouTube about that, which would be major. Since they could snap their fingers and YouTube classrooms would be an awesome way to deliver the highest fidelity ceilings on on simulations. And we're sending in our model that, like, the sort of cheap crappy Chromebooks in classrooms, they need to have you know, some version, just maybe not not some analog. It doesn't need to be, like, Google Earth level. But that's probably actually the bar, something at that level of Google Earth But beyond that, we wouldn't we would serve, you know, maybe explore the higher cost thing separate. That's TBD. Right now, we're just saying, hey. Let's work out what how much gain we have by just setting a game engine in in place. Seeing how these different sort of mechanics feel. And then but likely, we'd have a space for essentially, like, the offline mode and then the high fidelity mode. That's probably, like, your testing mode with the teacher is our best guess.

Me: Mhmm.

Them: Mhmm.

Me: Yeah. That all makes sense. And I think, you know, one of the interesting so your seeing in these the cases where we know, knew what the horizontal and vertical were and put forward those in a contained sort of set of options. You know, it would be interesting. We haven't, you know, had enough opportunity to explore sort of how you merge that with a more open ended agentic, you know, exploration. But you could certainly imagine that the student is exploring within this world, encounter, you know, a bat and a snake and a something and somebody else encounters two or three other and then, you know, all seven of those are in the simulation, but you expose the three that they encountered, for example, or suddenly or they happen to be it happens to be afternoon for them, so you might do if we were doing things that are more sophisticated, you could imagine ways that you could still present something that was contained enough that it gave them a high chance of success at doing, you know, experimentation. And had spanned enough parameter space that they could, you know, sort of explore things in meaningful ways. But it was you know, tuned in some way, shape, or form to the exploration that they've done. You know, that project based simulation integration, I don't think has been done nearly certainly not to the extent it could be and oftentimes not at all. Mhmm.

Them: Yeah. Yeah. And this vintage of simulation was ever any I know there wasn't a well formalized API, but was there some form of documentation already kind of attempt? Because presumably, there was a bunch of sims made in this vintage that probably

Me: Oh,

Them: wasn't just one person or maybe it was.

Me: you mean the the assessment ones? I mean, those had to communicate with

Them: No. The these that are on the screen. This particular I'm just like, if we wanted to

Me: Yeah.

Them: like you know, I looked at the code. It had it has something that I'm sure if I like, I can see where the sort of molecules are being defined. What was that ever sort of documented or, like, a p you know, in that sort of mindset of, like,

Me: Not well enough, I think, I would say. I looked to Leslie to say more, but, you know, I think not well enough. Is is the short answer. Know, we we've we've gotten examples of things where it's talked to other stuff outside. But it's been more one off than than not at the best probably.

Them: Yeah. And if you're talking about changing the SIM itself, I mean, you need to be a scientist who understands the science well in order to know what to ask for out of the parameter space. Because I can see in this if I share my screen. This lav inter

Me: Yeah. You got it.

Them: You all see my screen? Or Not yet.

Me: It's got it's coming up now. It'll it'll be coming up.

Them: Oh, y'all see it? Okay.

Me: Oh, you can try sharing it now.

Them: How's this?

Me: There we go.

Them: So the I assume this lab interactive browser was meant to

Me: Yeah.

Them: mean, was essentially meant to accept a

Me: Yeah. The

Them: you know, carefully configured sort of

Me: around with the JSON, essentially. Yeah.

Them: That's right. Yes. And

Me: Mhmm.

Them: Right. And and what I'm saying, although it's a little bit more obvious when you're dealing with macro structures like a wall. Than than some of the atomic stuff, which tends to be very finicky and breaks very easily if you say something that's kind of weird. But you know, you see how long these are. They're very verbose. Yeah. Yeah. And and if you skip a you know, if you skip a thing or you, you know, ask for a thing that's nonsensical, it basically doesn't have any control in it to deal with that gracefully. Right? Yeah. So these were designed originally to be kind of like, carefully tuned. You stick the model in and then freeze it in the URL for the the actual model. But it may have some finickiness if there's, like, Yeah. I wouldn't I wouldn't recommend I mean, you're welcome. To try, and you may even, you know, have some initial success. Tweaking around. But, you know, if you were, for example, to try and make two layer walls with insulation between them, I would be kinda surprised if you were able to get that to work. I would be kinda surprised if I were able to get that to work. Right? Like, I would go to the guy who fortunately still works here, on these and ask him to, you know, to to give me another another virtual

Me: Yeah. I started I mean, a good example. I started doing exactly what you were envisioning with the the CEO two ground based Charlotte ahead of you asked for it because I thought the same thing and got away as and, you know, one of my things worked, then it just stopped working because I listed one of the molecules wrong. And I, you know, I've decided not to spend more than a half hour debugging it because I missed a somewhere in the giant list and there's something it was yeah. So yeah. I mean, yeah, it works. It definitely can work, but, you know, you'll you'll bump into walls because it's not intended to be

Them: Yeah. That make that makes sense.

Me: it's fragile sometimes. Mhmm. I mean, the more interesting thing with the molecular stuff is that it's, you know, stochastic and works because it's stochastic, but that bites you in the butt. Sometimes as well. You're like, oh, actually, you have to pin those through those sets of molecules. On the side or they're not gonna or you have to really tune it so it you know, in the right temperature range even though it's not supposed to be. Yeah. Little bit of that stuff is more

Them: Right. Which is exactly what I mean

Me: bespoke.

Them: Like Yeah. Yeah.

Me: Yeah.

Them: Exactly what I mean by, like, you have to be enough of a scientist to why your model is nonsensical. And and, therefore, it is doing exactly what you it to, which is something insane. Right? That's, you know,

Me: Right. Right. All of which, you know, doesn't undercut the fact that we've got 300 of them and we've found, you know, five thou 500 situations where we can use it. So, like, you can make it dance. You know, you just sort of have to

Them: Right. Right. Now there's, like, a the you know, useful

Me: know how to use the yo yo.

Them: just from a technical there's a diff that goes from this to this that is

Me: Mhmm.

Them: you know, that's a help that that is a helpful outcome because then we can sort of see

Me: Right.

Them: you know, the you know, I can envision what it would would be, and then there's some fragile bits here

Me: Well and and to be clear, you know, if we're

Them: that

Me: if we're in a point where, you know, we're like, oh, okay. Here's a unit. And we need 10 of these somethings, and they're in a genre or actually we need to reproduce it a 100 times across the next four unit. Like, then we're in a world where, like, oh, okay. Actually, you know, cordon that off into a p that's that's work, but it's, you know, not we don't have to do all 200 of them you. Like, we can cordon it off and box it up and make it work. Right?

Them: Yeah. Right. And this is what I mean about, like, the scoping part being so important. Because if I know what your goals are, then we can look for those moments where a little bit more effort on our part to make something repeatable or extensible is is worth the dime. Right? You know? Because then you then you can make a 100 sims you know,

Me: And

Them: Mhmm.

Me: Yeah. We're not it's not, like, all glass blowing. Like, you can you can make a mold. Right?

Them: Right. Which is exactly what we did for Desi and exactly what we did for Fos. Right? We we spend enough time talking about, like, their their aspirations sort of across the project. To be able to make the mold that would let you, you know, do things repeatedly. And are any of the sus usual suspects like the Pearson's wanting revamps of the some of this prior work, like, to you know, in in this month Not not so far. No. Not yet.

Me: But, yeah, I mean, it's it's individual probably the the the assessment world is still toying with this in in various levels, for example. So we're hopeful that the field moves forward. But

Them: And and and yet I could answer that question in the reverse because, as I mentioned, this was a five year that the assessment thing was a five year long project. And so we did the first year's worth, which we did eight I think, and learned some things, and some of they threw away, and some of them, they extended or asked for changes. And then we did another year, and we learned more. And we changed the old ones and did the new brand. So in another sense, we've actually

Me: Right.

Them: revised them all the time. You know, just just depends on on which phase of the thing you're talking about.

Me: Mhmm.

Them: And what worries you the most about the I mean, we're showing I'll show this live because this screenshot may not actually be clear that this so at an engine level, from a gaming point of view,

Me: Yeah.

Them: love that this, you know, is just do doing what we want to start with. Sure. Gonna hit the

Me: Mhmm.

Them: ceiling eventually. Presumably, there are some gotchas in here where, you know, besides, there's just not running on a Chromebook in a in an offline Yeah. It's like, what? Would concern you about, like, this direction? And, you know, I'm just curious from the earliest time point if you sort of I can I can definitely talk about that? So there are two things that we have had trouble with on Chromebooks, and lord knows we've had our share. Even with many many pieces that we haven't even shown you or talked about. Yep. The first is the tiling. Right? Like, you've got textures in here. They have some resolution to them. They're not terribly high. Right? Your trees get pretty fuzzy when you get up close. In the same way that maps get can get pretty fuzzy when you you know, zoom into your town too much. We just had a thing go not so well in Hawaii with a volcano simulator because the maps had too much resolution. And it was literally It's all running locally, right, as a Yeah. You had a they had a download them because what? Their Internet connections are also similarly not really all that great. Right? And so, you know, just just zooming in and out to see various places where you were now simulating a volcanic eruption, forget about the forget about the simulation of the lava flow. It's itself, which was also somewhat time consuming and had performance issues. But they couldn't even get that far because the map that they needed to be looking at was, you know, was overly restrictive and required too many bits. So you gotta be careful. Which, you know, is why we often will do many, many things

Me: Nice. Yep.

Them: Yeah. Sure. Right. You're doing the right thing, which is do the physical experiment and see what happens. Yeah. I'm curious if if you yeah. Because this is what we we started with, like, the kitchen lab sort of, like, everyone can, in theory, do this with enough time and materials. Ideally, just like, stuff lying around. Yep.

Me: Yep. And we we've had whole projects doing that, you know, a decade ago. Yep.

Them: Yeah. And then it's very sort of, like, synchronized. We are you know, when we're moving between like, assuming we have a strong enough Internet connection to one computer in the

Me: Mhmm.

Them: classroom to test the designs, it could be. Even asynchronous in some sense. That's something I'm working on now. It's like, well, can we actually, like, count on a YouTube level bandwidth, you know,

Me: Mhmm.

Them: for a single device? The answer is no. The other problem that though, that we ran into repeatedly, and you'll notice that the thing that I'm not saying is the simulation. Calculations because those are actually typical relatively straightforward even if they are you know, finite element simulations where you have to calculate time steps. Even those you you can do it. Right? It's fine. The JavaScript processors are usually just fine. The problem is that that browsers have very nonuniform handling particularly from OS to OS. Of the various three d compositing protocols. And there's actually too little constraint in the average three d library to tell you which one will render reliably on a PC, on a Mac, on a tablet, on a whatever. Like, I had multiple situations particularly given the broad swath of devices that we had to support in Massachusetts classrooms. Where they would say, we can't see the sun in this, you know, simulation of, you know, the earth and the sun system. Like, well, it's there. We see it. Right? I can send you screenshots of it. I can demo it to you, and they're like, great. But it doesn't show up on on this computer. And you know, we would build then five or 12 different versions of the three d renderer until we found the sweet spot. Right? Like, we experimentally figured out which rendering would work on you know, on Windows, the latest version of Windows. And which one wouldn't. And pray that that one wouldn't cause rendering problems on any of the other systems that we're dealing with. Right? So, like, honestly, those are the those are the bugaboos. And they tend to happen with these three d modeling engines. Right? It's it's very few other technologies that give me give me fits like this. You know? Mhmm. Yeah. No. That's help that's helpful. That's what we suspect. Is the shape of things, and we're assuming the right model over time is kitchen lab physical experiment plus Chromebook two two d, three d, you know, maybe a light three d type simulations as the kinda, like, guaranteed back And then if we have a little more spice, then we well, at least learn much bang for the buck do we get with the modern game engines. Fort Fortnite, by the way, is, a 100 gigabytes. No normal

Me: Right.

Them: person is going to install it. Like, I'm really shocked at what kids actually put

Me: Yeah. What what are they and and Unreal help

Them: put up with to

Me: you until the machine crops up, but what's the I I'm not familiar with the specs there. You're not you're not gonna run it on Chromebook, I assume.

Them: Almost. Almost or not, unless it's their latest and greatest Google is pushing Chromebook Plus or Pro, and they have some name for it. So that, you know, there's there's something this year they everyone to upgrade, and that might change. That actually probably would would handle would handle it. It's just

Me: Right.

Them: maybe three times the price. So it's and they're pushing AI, some AI neural acceleration on there, which is interesting to us because we could run our conversational

Me: Mhmm.

Them: AI all in classroom.

Me: Mhmm.

Them: That's that's stuff I'm experimenting with currently with OpenAI just putting out finally permissive open source. Small, that's about

Me: Yeah.

Them: capability of what we're using today and paying paying for. So

Me: Mhmm.

Them: Right.

Me: Interesting.

Them: Right. Alright. I'm sorry. I'm gonna have to go, but I just give me give me a deadline for the for the thing, the plugging the plug in thing that we talked about. When do you Yeah. I think with just the just the you know, get getting don't know if it's, like if a week is crazy to re the rearrangement as opposed to the new new fee any of the newer stuff? Yeah. I'm just start right. Just talking about the rearrangement and I and, you know, and two URLs which give you two materials. Right? Yeah. That's, that's ideal because we can pop that in next week on some of the three d stuff and just get a start you know, get a vibe check on on integration. No attention on visual forgot about it. But maybe. I'll say maybe. Yeah. Yeah. Our time constraint is our next George meeting is we got September 8\.

Me: K.

Them: So that's what's driving our Gotcha.

Me: Good. That's great. Well, Leslie is around this week and and not the week after. But if we feel like there's gonna be handover and back forth, we might wanna, you know, make sure that we're looping, you know, by early next week or end of this week just to know about timing in case somebody to hand over to somebody else internally. Mhmm. Probably is. Yeah. Scott is fine. Yep. Cool. This is great stuff, and I think some of that ideation is is the right, you know, level for the next conversations, you know, as we move forward, as you have those meetings and and start to hone in, all that seems cool, and I'm actively trying to not talk about sensors and things, but we've done lots of probing sensors and what have you. So if you're trying to do kitchen labs, there may be other ways to plug in on that too. So more more to come. Cool. Good stuff. You both. Bye. Mhmm.


