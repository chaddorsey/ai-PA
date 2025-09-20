

**CODAP development discussion**
================================

Attendees:

Scott Cytacki,William Finzer

scytacki@concord.org,wfinzer@concord.org,lbondaryk@concord.org

2025\-08\-20T16:00:00\-04:00

\-\-\-\-

\#\#\# CODAP v3 Beta Status \& Bug Triage Process

\- Current bug counts driving development priorities

\- 13 items in internal beta (mostly from current testing)

\- 40 items in public beta list (not yet triaged)

\- Need to determine if 40 is actually 20 or 100 after proper review

\- Making forward progress: bugs fixed \> bugs added on average

\- Bill and Kirk to conduct triage pass next week before Leslie’s vacation ends (by Aug 29\)

\- Move prioritized items into Dev Team Sprint 16 \& 17

\- Use internal beta bucket for items needing discussion

\- Resume monthly bug triage meetings when Leslie returns (similar to old CODAP development process)

\#\#\# User\-Centered Prioritization Framework

\- Testing prioritization models for feature decisions

\- Pick 3 features team struggles to prioritize

\- Survey \\\~15 beta testers with two questions: “How would you feel if you had this feature?” vs “How would you feel if you didn’t have it?”

\- Scale: Like it, Expect it, Neutral, Tolerate it, Dislike it

\- Chad to send prioritization methodology links

\- Kate to help with beta user surveys and feedback collection

\- Opportunity to engage community in development decisions

\#\#\# Public Release Timeline \& Strategy

\- Target timeline aspirations

\- Public beta: October 1

\- Public beta 2: November 15

\- Public release: January 1 (New Year, new CODAP)

\- Resource allocation: \\\~15\-17 weeks developer time available

\- Ongoing beta model with regular releases until public launch

\- Pip Arnold testing in classroom next week with feedback button

\- Need to check in with ESTEEM team on beta usage

\#\#\# Technical Issues \& Implementation Notes

\- Critical switchover considerations

\- V2 to V3 document format transition requires extensive Activity Player testing

\- Jay and Rebecca already saving in V3 format during testing

\- Legacy document issues should be identified through current beta testing

\- Performance concerns flagged by Scott

\- WebGL crashes with too many graphs or \>50K points per graph

\- Memory usage climbing to 800MB\+ for long\-running sessions

\- Touch device support needs improvement

\- Bill planning transition from programmer role post\-public release

\- Radar plots needed for DataGoat project (sports analytics use case

\# Resources

\- Kano model – overview article: \[https://www.productplan.com/glossary/kano\-model/](https://www.productplan.com/glossary/kano\-model/)

\- Kano model – in\-depth explanation and guide: \[https://foldingburritos.com/blog/kano\-model/](https://foldingburritos.com/blog/kano\-model/)

\#\#\# Action Items

\- Bill \& Kirk: Complete bug triage and prioritization by Aug 29

\- Chad: Send prioritization methodology links to team

\- Chad: Connect Kate with Bill for beta survey coordination

\- Bill: Move prioritized bugs into Sprint 16/17 buckets

\- Scott: Create Jira story for WebGL/memory performance issues

\- Team: Establish regular monthly triage meetings starting September

\-\-\-

Chat with meeting transcript: \[https://notes.granola.ai/d/fb52daf8\-50f8\-424d\-91d7\-3fbd83e9f121?source\=zapier](https://notes.granola.ai/d/fb52daf8\-50f8\-424d\-91d7\-3fbd83e9f121?source\=zapier)

\=\=\=\=\=\=\=\=

\-\-\-\-

Granola link: https://notes.granola.ai/d/fb52daf8\-50f8\-424d\-91d7\-3fbd83e9f121

\=\=\=\=\=\=\=\=

Transcript:

Me: Good. I don't have to delete the other one. Well, I will delete it, but we can reschedule.

Them: Good.

Me: 101\. Or have it for thirty seconds right now. How are you doing?

Them: Oh, for personal reasons, I'm not doing very well right now.

Me: Oh, I'm sorry to hear that. Not fun.

Them: Hello?

Me: Scott?

Them: How's it going? That help you gave me the other day helped me get to understand that the problems were are very deep. Great. I got so frustrated yesterday. I just tossed in the towel.

Me: Oh, removing the wool from our eyes is always informative. May or may not be know, a positive mental or emotional move, but at least knowing better than not knowing, I suppose. We're discussing the deep. The deep underlying problems Bill was uncovering things to Scott's, you know, architectural diving. Which I know I know more know more about than I just described. But

Them: I'm I'm assuming that we're talking about story builder or something else. Yeah. Story builder. Yeah. Goodness.

Me: Imagine Maybe not a hard guess. Either that or recreating most inside of code app is fine. One of the two. Right? Yeah.

Them: Oh, you have plans, do you?

Me: There we go. It's just her secret. So I threw this on the meeting. Putting the kibosh on a meeting that Bill and I had because it was available and Leslie is still available. And those two sentences don't happen very much, for the next week and a half. So I think our main goal is here is so code app work can progress intentionally while Leslie is on vacation. To start to establish a working understanding in what whatever kind of rule book we need for development that goes into mid September. So that things don't pause or Leslie doesn't come back and have five of those stickers instead of one. When she returns.

Them: September and and really my hope is, like, and and beyond. Right? Like, if I understand how we are

Me: Yeah.

Them: how we are triaging and how we are elevating stories, you know, now that we've passed this internal beta marker. Then then we can all just proceed, and things will make sense. You know, there will be the usual contention for resources, but at least we'll know kind of what we're doing, what the rule set is.

Me: And it it feels like to me that there's sort of

Them: Know?

Me: understanding a workable public beta line and developing to to that, which may be above the the full set of tagged stories, but is, you know, somewhere. And there's sort of ongoing process beyond that. And I think they're sort of one in the same But I'm also interested in models for prioritization. You know, Bill, you probably don't remember nine years ago, was just looking at my notes in Evernote and, you know, I discovered prioritization models and thought, oh, we ought to put bring that out somewhere. Think there are one or two that might actually be really helpful in figuring out which of the 25 features that we all want we should work on next in order to maximize people's usefulness and delight. So might be able to trial that over the next, you know, month or or two. Mhmm.

Them: And just to be clear, the when you say features, nearly every feature is already implemented.

Me: Right. Yeah. Yeah.

Them: Suppose that some features are not have bugs in them or are not fully implemented.

Me: Fair fair enough. Yeah. Exactly.

Them: Yeah. I I really mean well. Almost entirely bucks, right, at this point. Is what we're what we're doing here. Yeah. But they are bugs in features

Me: Yes, exactly.

Them: that prevent the feature from being useful at all.

Me: Yes. Would would you like feature x to work? Is

Them: Right.

Me: a bug, but it's also a feature. Yeah. Mhmm.

Them: Yeah. So here, I'm you know, like, again, I this list used to be none, and now now has 13 items in it because I told Zach to kinda stuff in here. So And I haven't had a look at these. Yeah. Sure. But just to kinda, like, get a sense of the the size of the issues,

Me: Mhmm.

Them: There are 13 things in here, which think are mostly from this internal beta test, maybe a few things that got slopped over from a previous sprint. Then there are 40, in the public beta list. I have not triaged these nor, again, do I wholly feel competent to do so. Mean, I'm better than I was, but still, Could be a good person to go through that list in particular along to pairwise with Kirk. We could make good decisions And move them into public release or down even below that. Yeah. Like, that would be amazing. If if the length of this list is not actually 40, but is actually more like 20, you know, then then I guess that would make me feel like, okay. Fine. I know how to put that into the next, like, several sprints, and then we can think about a date that we wanna announce a beta and blah blah. If that list is actually a 100 and not 40, then we have a different kind of problem to address. Well, I think we've reached a place where we are making forward progress So the number of bugs added to the list, even with this the bugs from the beta on average, is fewer than the number that we're quashing. Yes. That that feels hopeful. But, you know, back to Chad's point, like, I don't know if there is a metric that one could apply here. Other than this is not a bug anymore. Well, you I think the general idea, I think I've said this before, is to put yourself in the mind of the various beta testers, various people that will decide to be beta testers,

Me: Mhmm.

Them: That's not an easy thing to do. And say, how would they feel about this In particular, would it prevent them from using the beta with their classroom And if so, that's probably something we wanna fix for the beta. Would it turn them against Kodap in some sense, if they were relatively new to Kodap. Then that would be worth fixing. That's on the one hand. On the other hand, is this something that only a small very small percentage of beta testers will even notice?

Me: Mhmm.

Them: Those can be pushed down to to public release.

Me: Yeah, I think, and my guess is that putting ourselves in the mind of the user's might end up with sort of two piles on a certainty scale. Like, there might be one pile where we're pretty certain, we can make that, you know, prognosis or that that, assessment, and there might be another pile where we're we're unsure or or we have variation in what we, would anticipate in the minds of users. And it could be in this world. You know, I can send some links on after this, but there are nicely systematized ways of asking people about some of those things. And given that we have a cap captive audience of beta users, you know, we might be able to even choose a handful

Them: What was the question?

Me: of these and even poll people if we get to that point. What's that?

Them: Chad? What would you ask them?

Me: You asked some two questions in this kind of model. One is how would you feel if you had the feature or maybe the feature were working? Another, how would you feel if you didn't have And the answers are I like it. I expect it. I'm neutral. I can tolerate it. I dislike it. Essentially, you get a two two factor scale that you can, you know, do some plotting on and becomes a fairly systematic way to say, oh, okay. I guess people actually want this one. Mhmm. So there might be a way to do that. And thinking about pose because I'm writing here. I mean, of these things might actually be ways to engage community. Some of this discussion might be ways to start to think about you know, ongoing development mode as well. We don't have to do everything at once. But it'd be interesting to try that with a few things at least.

Them: Scott, do you have a perspective on this issue?

Me: Mhmm.

Them: Not really. I mean, other than what Chad was just saying, I think it is a good way to engage community to get them to at least provide input about whether they like want a feature fixed or bug fixed or not. Whether we actually do it or not, just the fact that we're asking them engages them. And that was one of the things mentioned at that open source conference that I went to. So

Me: Guess is most of these bugs are too abstruse to ask that about anyway. Right? But you might be able to find five or six that would actually be liable that way.

Them: So with Zach's departure, we're short on resources to bring this kind of

Me: Mhmm.

Them: user poll about.

Me: I can I can get some help from Kate if we need to for for some of these kinds of things? Mhmm.

Them: That would be great. Yes. And I I always endorse any conversation that happens with a user who is not somebody at the Concord consortium. Always

Me: You have and you haven't spent as many that of the discussions, Bill, but one of the things I've been pushing is sort of more general user discovery across the organization in various forms. The Pose interviews were one example. We're doing conferences and having focus groups in more general, you know, Concord trying to get a sense of people's needs. So I think this fits in that same vein. Mhmm.

Them: Right. But I I would not personally want to be the person to say, okay. You and I are now going to look at 40 head

Me: Right. No. I I I agree with that as well.

Them: Do you care about this? Do you care about

Me: Mhmm. Right.

Them: Right? Like, sounds

Me: No. Right. So so I think I think we need to do that first pass, maybe even two of the passes that you were talking about, Bill, and then, you know,

Them: painful.

Me: may find a handful of features that are really worth asking people about. Mhmm.

Them: Yeah. Most of the most of of the time, whether it should be prioritized for the beta or not, will be straightforward. And there will be a handful especially a handful that might we might say, oh, that's gonna take a a fair amount of effort.

Me: Right.

Them: And those we would want that we would benefit from outside input.

Me: And that's and that's where some of these models was just going back and rereading very skimming this kind of model. I mean, its goal is to basically say, what do people want? Yeah. Fine. But what can we do also I mean, what can we do is another part of this. Right? So if everybody wants that costs a million dollars, it kinda doesn't matter. Mhmm.

Them: Yep. The other part of this that came out when we were releasing the internal data was, like, figuring out how much of this do tell people about when they start using the beta. Like,

Me: Right.

Them: sort of the other approach is to say, you know, if you're worried that they're gonna hate us because this isn't working, if we make it clear in the beginning that it isn't working and we know it's not working, there's probably a class of ones that are would be okay with that kind of explanation. I'm sure there's other ones that are, like, even if you tell them that, they're gonna be really annoyed and

Me: Right. Yeah. Yeah. No. I think you're right. You're the the goal is not to release

Them: upset with us. But

Me: the public beta with an overlay screen that says, look at look under the couch for the big red wine stain. Right?

Them: And I so can I switch topics for a moment and try to understand? Let's suppose we've come to some about which of these items we're fixing. Hopefully, maybe not all of them. And which of these items are we talking to users about? Maybe some of them, maybe not. Okay. Now we have that build in hand where we can fix whatever the 20 or 30 or maybe even 40 issues. And we do what happens then? We put that we advertise that on a different v three URL on the code app. Web page. Or something. And a blog post

Me: And a little beta sticker when you're in code app so that you know you're getting into or something. Right? Yeah. Right.

Them: Which there really is for the private beta.

Me: Yep.

Them: Yeah. So I have I have a button that takes you to a feedback form. Am I leaving that there? Do we leave that there?

Me: Yeah. Definitely.

Them: Yes. We do. However, if you're

Me: Mhmm.

Them: do you want it there when a teacher is using it with their students? Like, should the students see that button?

Me: I would be I mean, if they're choosing to visit with students, then, yeah, I'd I'd much rather weed out student, you know, silly feedback than not get user feedback from my perspective.

Them: So you're in favor of leaving the button there?

Me: I would hit the button there. Yeah.

Them: No. It'd be fine with me. I just wanna confirm because I feel like when we we're talking about this before with our own research projects, we decided we didn't want them missing the button. In our research projects. Maybe still would be the case. So that's Hip Arnold is going to be using this in a classroom next week.

Me: Great.

Them: Great.

Me: Awesome.

Them: With with the button.

Me: Nice.

Them: With the button.

Me: That's great. Button and all, we'll take it. That's wonderful. That's a perfect test.

Them: And what about the esteem folks? Unless some of this some of the feedback Zach has gotten has come from them, I personally have not heard from them. Okay. Yeah. I mean them to to take it seriously.

Me: I mean, I

Them: They have a lot at stake. That would be a huge

Me: think I think if it were an absolute stopper, we would have heard from them already, but I'm sure there are nuances. Mhmm.

Them: Yeah. No. I I would I would love I would love to hear that Holly Lynn was using this. But I can ping ping the group and say,

Me: Yeah.

Them: how's it going with the beta? Mhmm. Mhmm. Okay. And then what? Then we wait another whatever month or some and and see what see what emerges. Well, another model is you have kind of an ongoing beta with regular releases and it just stays in beta. Until we're ready for public release. And I don't I've that's what I would

Me: I think we're I think we're definitely in that mode regardless.

Them: choose. But

Me: And, you know, and I think it doesn't necessarily matter, but we will ultimately hit question of when we will remove the the button, you know, that maybe neither here nor there. I mean, Gmail took five years, but if or it may matter because we see that people aren't using the beta when they should, but then it's a publicity problem, not a you know, software problem. And most of this is about where we move the buttons on the web page anyway. Right? Because you're not take away v two entirely right away, and you're just

Them: Oh,

Me: gonna try to lift up v three. Mhmm.

Them: well, when we do a public release, all of the v two URLs will do v three.

Me: Okay. Alright. So then then that that decision point will be important.

Them: That's what it with the what yes.

Me: We need to think about criteria for that.

Them: Yes.

Me: Down the road. You have in your head, Bill, is that switch point measured in, you know, months you can count on one hand, years you can count on one hand? Do have any idea what's what's your thinking? Mhmm.

Them: Well, I I think it's between this many and this many.

Me: Months or years?

Them: No. No. Five months or

Me: Okay. Right. Just just checking.

Them: ten months.

Me: That's good.

Them: Ten I mean, it's not and it's not really based on time. Right? It's based on issues, I'm guessing. Yes. And a public release can happen with will happen with us knowing about many remaining issues.

Me: Mhmm.

Them: Yeah.

Me: Just as v two has a backlog of issues, we're deliberately not

Them: Backlog. Yes.

Me: Yep.

Them: Yeah.

Me: Yeah. I think that makes sense.

Them: And and and the thing driving it, at least, one thing, is the fact that we don't wanna continue maintaining v two. So reports a bug, we don't wanna have to try and fix it in v two when we've got this v three thing.

Me: Mhmm.

Them: This Pretty much

Me: Mhmm.

Them: already adopted that posture. M Okay. And I guess I hope that we can maybe at this time slot, maybe this will be, like, the first of many have, like, a regular triage meeting at least once a month. Just to say, here's the new stuff that came up. And do we think it's more important than the old stuff? Or does it just go to the bottom of the list because it's not a big deal? You know? What we used to do in the long ago days of codap development was have a regular bug We called them we called it a bug meeting. Mhmm. And the purpose was to go over bugs and make decisions about them. And that worked well. It's time consuming, Sure. I mean, Kylie and I do a regular bug triage every two weeks. These days, by and large, we wind up just slacking each other because there's, like, two bugs to review. And either she has an opinion or I have an opinion, and we're done. But we are not doing that with the code app bugs because we're not qualified. So, you know, if at least once a month, we could you know, either in this time slot or one other that gets suggested, have you and Kirk and whoever else wants to play. Bring bring that back, I think the time is probably right for that. Yeah. I would say when you get back, let's let's begin that.

Me: And and I think if that might be a good opportunity to just play in the meantime since we have these internal beta people we know who put a little skin in the game, with some privatization. I'm scrolling down in these articles that all send on links to you. But you know, when it's the one that describes launching your own study, says, pick three features or ideas at most that you're struggling to prioritize. Find 15 people or so for a demographic. And then send them these two questions on the So, I mean, I think that's something that we might be able to aim to do is find three features within this that we don't know which one to work on first. You know? And, you know, we we could use that as a chance for our to try to ping people and take over a little bit of the beta monitoring. Mhmm.

Them: Another strand in this process is to, rethink

Me: Mhmm.

Them: the ramifications of the switchover and make sure that we've covered all of the consequences of making the switchover. And there is one important ingredient in the switchover, which is switching from the v two document format to the v three document format.

Me: Mhmm.

Them: So that when Codep saves, it saves as v three. And that requires some significant testing, especially in things like Activity Player, to make sure that users will not notice the difference, basically. Yes. And for I have been using Jay and Rebecca as my activity player yeah. And they have been saving in the v three format They're not using v three. Yeah. Wait. I'm sorry. They are saving in v three? Yeah. They they've been saving in v three. And if I can't remember sure, but I'm pretty sure when we set it to save in v two, that doesn't apply when it's running in the activity player. I think it still does v three. I see. Well, that's good to know. Yeah. Well, thank you for enlisting them. Whether they liked it or not.

Me: Is it is the critical question there mostly the matter of does the v three format work entirely, or is the is it about finding legacy issues with somebody who resurrects the document from 2021 or something.

Them: The legacy issues will all would already have been uncovered by

Me: Okay.

Them: Rebecca and Jay to the extent that they do

Me: Right. I'm just wondering in general in the public if there are if we how well scoped we

Them: Well, that is sense.

Me: know, we have how well scoped our understanding of those legacy things are. Mhmm.

Them: In a sense, because of the beta, is dealing entirely with v two formats. We're

Me: There are issues that are gonna happen.

Them: all we are already they were already gonna happen. Right?

Me: That's useful.

Them: Yes. So I think it'll probably be fine to switch to v It's just that when you you can't go back is the thing. You know? Like, so if you when we start saving in v three format, you can't then go back to v two code out v two, open it there. As far as us finding issues because the way we're p the way Coda v three is currently working, it's actually more complicated now than if we were just saving in v three directly. So Exactly. We we should hopefully, we will find everything over the next few months if there's anything out there. And I lost the thought. Never mind. It'll come back. Yeah. I'm interested in in fact that I don't see like, you can see pretty much every one of these bugs and or features that we didn't quite get to are, you know, falling into this UX affordance. Bucket One or two, you know, like, undo things, but a big one will be support for touch devices. Which we haven't directly tackled but fortunately, works pretty well already. But not perfectly.

Me: Yeah, that would be, if you were choosing you know, three meaty things to try to dig in on, that might be a good example of something to ask people about. I'd be really interested to know whether people were indifferent, you know, to or felt strongly about the touch device question.

Them: And we already know that some people feel very strongly about that

Me: Alright. Some people feel very strongly about it, but, you know, this is just distribution of people and size and emphaticness.

Them: Okay. So Bill do you have time in the next I don't know what Like, we're we're going to plan more code app work on September 2\. Mhmm. More we're gonna be returning to a, you know, couple of couple of two, three weeks of concerted bug fixing with a couple of engineers. So I I would plan on making this pass, with Kirk next week. Okay. Alrighty. And then when

Me: Does that need be early next week or late next week, Leslie? I know you're sort of semi available next week.

Them: I mean, if if you need my help, and I bet you don't, but

Me: But I don't have your time.

Them: if you need my help, then it just needs to be by end of day on Friday, the twenty ninth. If you don't need my help, then you just need to be sure and stack up the bugs that you care about in not the teal sprint because we won't be using these anymore, here, I can put, like, maybe this one into this into the next real sprint, which is find the sprint field. It's called the 16\. Okay. That's good to know. And is that in already present here? It will be now because I've just added I see. At least one. So question is where did it show up? You might have to reload after doing that. Yeah. Maybe. It'd be nice if we're not at the bottom. I don't know how it orders them. Probably alphabetically. Yeah. Uh\-huh.

Me: Authentically,

Them: So there it is. But you can see it. So, yes, put things in there. And if you have too meant then you can put some in dev team sprint 17 too. Which it already exists doesn't have anything in it yet. But doesn't have any code app stories in it yet. So as soon as you put at least one in, it will begin to show up in your code app. Page. Okay. And if we have things that we're not sure about, that we want further discussion about, where would you suggest we put those? I mean, maybe just internal beta rather than making yet another bucket. But Put them up at the top of that and

Me: Yeah. Right?

Them: Yeah. We could put a label on them. Just gonna search by labels. Yeah. Yeah. You could. You could I I only discourage that because for reasons that I do not understand, labels in Jira are forever.

Me: Okay. That's fun.

Them: I mean, it's not that they once you label a story with

Me: No. But you add to your

Them: something, it is always labeled with that Oh, it's

Me: your label clutter.

Them: Labels. Yeah. Yes. And they have not yet given me a way to clean up that clutter, which we discovered the hard way.

Me: You do it with the APIs on backdoor or something? I wonder.

Them: I don't know. There was a there was only so much time either

Me: Yeah.

Them: Kylie or I were willing to devote

Me: So

Them: particular problem. So but but, yes, one could make up a, you know,

Me: fair enough.

Them: discuss me label, and maybe that would be useful.

Me: I mean,

Them: Things too.

Me: probably more problematically for the entire system, but, you know, it could be a status as well, I suppose, in that done to do to discuss or something. But far be it for me to and that probably would mess things up in seven different new ways.

Them: I mean, unless you wanted to make

Me: Yeah.

Them: don't get me started.

Me: Exactly.

Them: You should be able to use that kind of feature one off, but you can't.

Me: Uh\-huh. Yes. Exactly.

Them: So, Leslie, what's what's your,

Me: Mhmm.

Them: estimate of when we hit public release? I would ask that question a different way. I would love for us to have a public release in January at the start of the new semester, New Year, new code app. I believe that we probably have on the order of fifteen weeks worth of developer time, maybe sixteen, maybe seventeen that I could liberate from the schedule. Towards that work. So I would have to think about how many issues you think you could fit into, say, sixteen weeks and take a look at whether we think that that is close enough or not so much. That's fair. But I think as piring to release on the New Year is not an estimate, but a good goal. Yes. Yes. Right? And and that's born of the fact, again, that I I can't personally look at all of these 149 work items. Like, I'm sure that I would have opinions about some of them, but I can't look at all of them and decide whether they're legit. Important. But you can, and I don't know how fast you can survey them. But it's starting to look like a number that's not impossible to go through. Right? The list is far far reduced from its former Yeah. I've gotten when I'm doing it by myself, I've gotten very good at at going through the list. But doing it with other people takes longer. Yes. Yes. Alright. Well so, you know, if if we can winnow down these lists, you know, I would be happy to see us do a public beta on October 1, and a public beta too on with possibly even subsequent mini releases in between, but you know, a public beta too, on November 15\. And then a public release on January 1 or second or something.

Me: Mhmm.

Them: Like, that would be amazing. Would be really great. And do we have enough funds in your estimate to make it to a public public release?

Me: Yes.

Them: For sixteen weeks? Yes. For a hundred and fifty weeks? No. Right.

Me: Right. Exactly.

Them: So somewhere

Me: Yeah. As the as the the person holding the keys of the funding, you know, I I can we can get to that public place. I'm interested in prior thinking carefully about how we prioritize and make decisions. Beyond that, but I think, you know, getting to a public release that we think is, you know, the right level, which sounds like we are, I think we can do that.

Them: Okay.

Me: That's cool. So it sounds like one action item was bill prioritizing the bugs in the and moving them into the sprint. Is that right? One action item is Chad mailing things about these development prioritizations. All the known action item is Chad talking to Kate. And, connecting her in with Zach and Bill to understand the beta survey people. Other action items that we think are important.

Them: I mean, Scott, I would look to you and Kirk to raise any like, this might not seem like a big deal, but we definitely wanna address this technical issue before we, like, go for real because it will corrupt every document ever. From now until the end of time, and don't do that. So one technical issue, not on that order, but has to do with WebGL. Mhmm. It's not too hard to make too many graphs and WebGL craps out on you. It's not too hard to put too many points in a single graph where too many is more than 50,000 I'm not sure what the threshold is. And, again, pixie points WebGL craps out on you. Fixing that won't be easy We'll have to decide how important that is. Hopefully, we can say we can defer it until after the public release. But I worry about

Me: Oh,

Them: blocking on his name because I'm making the correlation matrix of scatter

Me: Uh\-huh. I don't think he's using that many

Them: He's making a lot

Me: points, but he's definitely making dozens of graphs.

Them: Yeah.

Me: Yep.

Them: There's something related to that. Maybe the same issues that I've seen when I have a code app three tab. Open for a while. It starts to use up most of the gigabyte of memory. And multiple cores just sitting there not really doing anything. Mhmm. Let's fix that.

Me: Oh,

Them: It's no.

Me: Chrome Chromebooks are the GPUs on Chromebooks are just fine. So I was

Them: Not good.

Me: not

Them: I mean and we test this that beta with, you know, students with old Chromebooks, and seemed like it from what I overheard when my kids were doing it, it didn't seem much worse than the Kodak v two on a Chromebook. Maybe better.

Me: Oh, we've had the advantages students don't do things for more than forty minutes at a pop. Most of it in most American schools, it's twenty, but we don't need to rely on that. So Mhmm.

Them: Right. So then because of that, maybe it isn't critical.

Me: It doesn't sound like a

Them: But that's just something that I've noticed. It's fine. Great.

Me: doesn't sound like a feature.

Them: You. And you to make a Jira story about that? Sure.

Me: That's

Them: Yeah. Like, honestly, really, you didn't write that down. Alright?

Me: I

Them: No. Because it's too, like, random. It's just, like, oh, alright. I just saw that it's using 800 megabytes. To figure out why or what it was what is really hard. So Yeah. Yeah.

Me: But, yeah, we have to look at the last seventy minutes of

Them: But

Me: of console output or whatever. Right?

Them: So, Bill, when we are rendering plots with lots of points, where lots is some number that we pick. A thousand or whatever. That's not a lot.

Me: Good.

Them: But we're But whatever whatever 20,000, I don't know, whatever you consider to be a lot. 20,000\. More than we can render comfortably because of the pixel depth of the screen. Are we not rendering fewer points because you're never gonna see them anyway? No. We are not. Should we be? Well, it would break the metaphor, the user model of what's going on. When the user does a selection, let's say a marquee selection, they expect that all the points in that selection are selected and that there shouldn't be an we don't have we've we've not tried to do anything different than render everything. Yes. I see. And deciding that we should do something different, which some advanced graphing software would do. Would be a big deal. Yes. I see. Okay. There are lots of issues that arise when you are really working with hundreds of thousands of cases and trying to represent them visually. That we don't tackle because that's not our use case. Right. Right. Alright. On an even more low tech note, just to protect the unwary, would we prefer to, like, just throw up a message that says, sorry. You're out. You're done. Don't make more graphs.

Me: Used you've used up all your data points for the day. Right?

Them: So we've begun Scott has implemented an exception handler that puts something in front of the user. And as long as what's happening is an exception, they would see that And I saw I can't remember if you were there when I saw it, Scott, but there's a way there's with the pixie points issue that I mentioned, there's there's a listener for that. And so you can detect that Pixi has run out of resources and put something up in front of the user. And I assume there's something about for WebGL as well, but I haven't I haven't investigated that. Right. Alright. And, you know, Chad, we just need another data and space and time proposal

Me: Well,

Them: that, you know, makes it

Me: it's it's in it's pen it's pending in NSF

Them: makes it a priority.

Me: right now waiting for it to be haven't said yeah. Waiting for them to say

Them: Oh,

Me: official word letter coming out. So

Them: sweet. What stage is it at?

Me: the proposal, which is a follow on to date and space and time is recommended.

Them: Oh,

Me: Like like many others. So we are

Them: printout functions.

Me: hopeful that the wheels continue to turn, and that's essentially the same proposal with classrooms instead of just theory. And less money because it's right now. But fewer people because it's retail. So Mhmm.

Them: Yep. But, boy, I can see that proposal being sensibly applied to this particular

Me: Mhmm.

Them: problem of

Me: Definitely. Yep.

Them: manually manipulate large swaths of data

Me: Yeah.

Them: a way that they can make sense out.

Me: It it it has teased out other interesting things that I have not you know, chased down about plug ins trying to load large amounts data from the data table, etcetera, and experiencing interesting delays. So yeah. Mhmm.

Them: One other piece of this is that once we have a public release I plan on my role becoming not a programmer,

Me: K.

Them: What? You're fired? I can't imagine.

Me: So we need to plan the party tomorrow as for

Them: Well, this is not a re

Me: for January. That's great.

Them: re did don't know if you said tired or retired. I certainly am tired. I'm tired.

Me: Tired is what she said. Yes.

Them: Tired. Yeah. I am tired. I should not been on an official retirement at that stage. I don't know exactly what I plan on but I plan to remain involved in data science education, remain involved in the nascent code app center for data science education at the Concord Consortium.

Me: Mhmm.

Them: And going to conferences and talking

Me: Wearing your benevolent dictator hat. I would hear yes. Parenthetically. Right? There you go. That's true too. Yep.

Them: taking off which I have been doing. So

Me: Cool.

Them: Sweet.

Me: Mhmm.

Them: Well earned. Thank you. I I do feel that I have heard it. Whether I well earned it is another question. Alright. So I know we're reaching the end of our time, but I wanna add one other question, for you to Moll. Is completely unrelated to any of this, which is that I believe that for a data goat, I am going to need radar plots. I think that's the right word. Those the spirally things. And I don't I don't know what you wanna do about that. Whether we just want, like, a new

Me: Sounds like a great plug in to me.

Them: tile type can build it in the plug in, which is a little weird for the project, but I could do it.

Me: Interesting.

Them: Or something. So just a thing to think about. Certainly, the default would in a research project, this is a perfect plug in. And then the question comes up as it did for the revised case card, Well, should this be brought over into main stream code app. And and then, of as usual, the question of, well, how will this benefit on the whole or will it get in the way of, beginners how to how to make that all work in good ways.

Me: Know we had some user centered prioritization framework we could use to determine that. That's the that's the perfect question. Where do we pull a plug in into main whatever the realization that most people don't even know these things are plug ins?

Them: Mhmm.

Me: And many people well, some people developing plug ins don't even know what the valuable plug in is. We saw the other person who developed a really nice web page that lived inside of Codep. Didn't use Codep at all. For its principal component analysis. It was like it was Jay was very excited that her person discovered how to write a plug in. And it basically separately loaded the data into the web page. And displayed a principal component analysis. And just sat there and, like, that's really nice.

Them: Yes.

Me: A web page.

Them: Why is it in Codep? Because it's not

Me: Because it's an iframe.

Them: Codep. Because there's data.

Me: Exactly. There are lots of ways you could link it, which should be really cool, actually. I've been interested in that but it was very intriguing to see that people were excited about plug ins and didn't really understand that there was interaction involved when they were really working Mhmm.

Them: And that let's say you're talking about build, though. It's not so much whether it's a plug in or not a plug in, but it's kinda like whether it's in the menu that makes it easy to add everyone to find and add to their documents. I think We call that plots. Plot types. Don't really appear in menus. They emerge from the things that you do. And so the question would be, is there something that you would do

Me: Mhmm.

Them: turn this dot plot or a scatter plot into a radar plot. And I don't know. I I will have to look at exactly the way that sports apparently you this is the way you evaluate athletes.

Me: Yeah. That definitely is true. I'm thinking about my vast experience with looking over my son's shoulder at Madden twenty four or whatever, but he's, like, screens the radar plots, which is basically, like, catching and running and somethinging and spinning. I know what they are. But you know? Yeah. A little bit spider webs.

Them: They look like spider webs. Right? That's what I can hear.

Me: Mhmm.

Them: Yeah. Yeah. Thank you.

Me: Yeah. And if you, like, if you were a circle on a radar plot, you would be the most awesome player in the world. And if you're

Them: Fine.

Me: just a tight end or the the you got one little spike. Right? Mhmm.

Them: Right. Right. Right. They show they show your your consistency. Over a variety of skills, and each sport has its own little metrics that apply. And it's you know, basically, the bigger the area, that is covered by the plot, the better a player you are. You can imagine the data structure, which is the at the parent level, you have the players. Mhmm. And then each player has categories of play and a score for that category of play So there might be a 100 players, and each of them has 20 categories. Right. So

Me: Right.

Them: that would be the number of cases that you have, and you would drag the players in and then you would drag the Never mind.

Me: Well, but it is I mean, this is a problem that I have encountered, you know, not that long ago where I want

Them: Yeah.

Me: to look at more than I didn't quite wanna make a two by two, but I wanted to actually make a three or four by whatever plot of categorical variables. When you get more to more than two categorical variables, then you don't wanna use a legend. Then you're in this radar plot land, essentially. Maybe not even categorical. Maybe quantitative, actually. They're quantitative.

Them: Well, this would be one categorical plot that list

Me: Yeah. Right.

Them: one categorical attribute that lists the categories.

Me: Right.

Them: 20 of them, And then for each

Me: Mhmm. Right.

Them: each of those, a player has a score.

Me: Yeah. Interesting.

Them: Great design.

Me: Yes.

Them: And data structure question.

Me: Yes.

Them: Too.

Me: That is the real question.

Them: No. Yes. And I found a nice, like, evaluation from somebody who does professional sports recruiting, that talks about a great hoary detail how he makes these plots, what kind of data you require for them, blah blah blah, the the ways in which they're important, how you evaluate them, and so on. So I just I haven't had a chance. It made my brain hurt. So our goal should be to do a demo for that person, and they go, oh.

Me: Yes. Exactly. Yep. Mhmm.

Them: Yes.

Me: Yeah. You're making me wanna grab now that it's in almost September, my O'Reilly book. I I bought the O'Reilly book about the data science in football. Basically, it's like learn learn r by doing football stats, and I haven't

Them: Yes.

Me: when when data got was first coming around, maybe I'll have to pull it out again. Alright.

Them: So shall we bring up the ten minutes?

Me: Let's great. Thanks.

Them: Alright. Thank you.

Me: Enjoy. Bye.

Them: Thanks. Thanks.


