## Campaign Tools Design

Campaigns are sold by Business Development and are currently the primary source of income for Figure1. There are several major considerations here, but one of the primary drivers has been to create a system that compares to legacy. 

A campaign is composed of 0 or more tactics, each of these tactics can have a specific start and end date and can be modified independently of the campaign. The campaign itself contains the targeting information that is inherited by each tactic within the campaign.

In addition to the targeting information, each tactic and campaign has a priority from 1 to 3. These are added together along with the specificity of the profession/specialty/subspecialty match to generate an overall priority number which is used to decide where in a given users feed a tactic will appear.


[TOC]



### Tactics {#tactics}

A tactic is essentially a case, a case can be composed of multiple content pieces such as an image series or quiz series. 

A tactic has 4 states available: SC_DRAFT, SC_REVIEW, SC_APPROVED, SC_ARCHIVED. Content is always gated through SC_REVIEW - if a change is made to a tactic in state SC_APPROVED, the state reverts back to SC_DRAFT where it can be moved to SC_REVIEW then moved to SC_APPROVED. This same process applied to tactics in state SC_ARCHIVED.

A tactic may have a start_date and end_date, both of these are optional. If neither start_date or end_date is set, then a tactic set to SC_APPROVED starts being served immediately. If a start_date is set with no end date, the tactic starts being served on that start date until it is manually stopped or the campaign is archived. If an end_date is set with no start_date, the tactic starts being served immediately upon the state change to SC_APPROVED and stops being served on the end_date.

The start_date and the end_date are resolved by day, not by time. The start_date includes the day and the end_date excludes the day. A tactic running from January 1st to January 3rd would run all day January 1st and January 2nd and stop on the turnover at midnight to January 3rd.


#### Tactic States {#tactic-states}



*   SC_DRAFT - This state indicates an in progress state
*   SC_REVIEW - This state prohibits further changes unless the state is changed back to SC_DRAFT. This state is intended for internal, client or legal review.
*   SC_APPROVED - Content in this state is eligible to be served
*   SC_ARCHIVED - This content will no longer be served.


#### Tactic Requirements {#tactic-requirements}



*   Tactics cannot be created in isolation, they must be created as part of a campaign
*   A tactic is always associated with exactly one campaign
*   A tactic always inherits targeting information from the campaign it is attached to
*   A tactic cannot be active if the campaign it is attached to is inactive
*   Tactics may be edited while active without the state changing.


### Campaign {#campaign}

A campaign is a set of tactics that are targeted towards a group or groups of users. A campaign can contain any number of tactics including 0. 

A given campaign can be in one of four states - DRAFT, REVIEW, ACTIVE, ARCHIVED. A campaign will only deploy tactics when it is in the ACTIVE state. The campaign state always overrides the tactic state. 

The campaign states move in the same way as the tactic states. Any edits when a campaign is ACTIVE or ARCHIVED moves the state back to DRAFT and removes all tactics from deployment. The state can then be moved from DRAFT to REVIEW then to ACTIVE. When a campaign is set to ARCHIVED, it removes any active tactics by setting the end_date and setting the state to SC_ARCHIVED.

In order to un-archive a campaign, all the tactics have to be re-deployed. This should be achievable in the UI by editing each tactic. Re-deploying a tactic does not mean re-creating, it only means that the start_date and end_date should be modified if applicable and the state changed from SC_ARCHIVED to SC_DRAFT.


#### Campaign States: {#campaign-states}



*   DRAFT - Indicates a campaign is being built - tactics may be attached in this phase
*   REVIEW - Indicates a campaign is being reviewed - tactics attached in this phase reverts the state back to DRAFT
*   ACTIVE - This campaign is running, any tactics attached are live as long as they are between the start_date and end_date with status set to SC_APPROVED. Tactics may be added or modified without the state changing, however changes to campaign priority, or targeting resets the state back to DRAFT.
*   ARCHIVED - The campaign has been stopped - all tactics associated with this campaign are stopped and the status for these tactics are set to SC_ARCHIVED. If a campaign in this state is re-activated, it will revert back to DRAFT status. Each tactic associated will require the states to be changed and start/stop dates reset in order for the tactics to re-appear.


#### Campaign Targeting {#campaign-targeting}

All targeting happens at the campaign level. Currently available options are profession, specialty, sub-specialty, country, language and verification status. Country, language and verification status are boolean matches, however the other 3 require further explanation.

The profession, specialty and sub-specialty are stored essentially as nodes in a tree. When you choose to target a specialty for example, you are choosing a node. The outcome is that every target is independent of every other target. If you choose a profession, a specialty, and a sub-specialty, the end result ends up being a search for profession OR specialty OR sub-specialty. The filtering is implied by the node you chose. 



*   Profession1
    *   Specialty1
        *   Sub-SpecialtyA
    *   Specialty2
        *   Sub-Specialty1
        *   Sub-Specialty2

As a further example taking the diagram above - you can choose to target only Sub-SpecialtyA and Sub-Specialty2. This would only target Physicians with Specialty1 and Sub-SpecialtyA and Physicians with Specialty2 and Sub-Specialty2. If you want to target all Specialty1 in addition, then you would add Specialty1 to the list. 


#### Campaign Requirements {#campaign-requirements}



*   Campaigns can be created without any tactics
*   All targeting is done per campaign
*   A campaign in ACTIVE state cannot have campaign properties changed without the state reverting to draft.
*   A campaign in ACTIVE state can have tactics added without reverting to DRAFT state.
*   A campaign in ARCHIVED state can be re-activated, but the state will revert to DRAFT. Any tactics associated will each have to be re-activated.
*   A campaign in REVIEW state cannot be changed without reverting the state to DRAFT.
*   Tactics are not active if the campaign is not active


### Targeting Priority {#targeting-priority}

The priority number overall indicates where a given tactic will appear for a given user. There are 3 places where this is determined, Level priority is calculated on the users match to the targeted profession/specialty/subspecialty, Campaign priority is set on the campaign level, and Tactic priority is set on the tactic level. Adding these three numbers together determines the final score, higher scores will appear more prominently. In the event of a tie, a newer tactic is given higher priority.


#### Level Priority {#level-priority}

Based on the targeting data, we make one assumption internally on priority. We assume that the more specialized a target hit is, the higher the priority should be. There are three levels, so we assign numbers 1, 2, and 3 here. Taking the example above, a user in Sub-SpecialtyA would have also hit for Specialty1, the most specific hit is the score returned, so this user would have a level priority of 3. If we have a different user that has Specialty1 but a different sub-specialty, this user would have a level priority of 2. 


#### Campaign Priority {#campaign-priority}

Campaign priority is user configurable per campaign, 1 is the default, the highest priority is 3.


#### Tactic Priority {#tactic-priority}

Tactic priority is configurable on the tactic level, 1 is the default, and the highest priority is 3.


#### Priority/Scoring Requirements {#priority-scoring-requirements}



*   Scoring determines the order in which sponsored content is served to users. It is derived by adding Level Priority, Campaign Priority, and Tactic Priority together
*   Scoring ties are broken by older content being served first
*   Priority changes to tactics require the tactic to be re-reviewed, Changes to the campaign priority require the campaign to be re-reviewed. Level priority is not configurable at the moment.


### User Feed {#user-feed}

Overall, the goal of this process is to make determining the order in which a tactic appears in front of a user as deterministic as possible. While there is some complexity here, the scoring system here is reasonably easy to comprehend. A higher score means it will appear more often in a users queue. 


#### Scoring {#scoring}

The score derived from the 3 priorities is used in 2 ways. First, the highest score will always appear first in a freshly loaded feed. Second, the score determines the number of times a piece of content will appear. For example:

Tactic1 - 7

Tactic2 - 6

Tactic3 - 3

There are 3 tactics here, each with different scores - the highest score will always be first, and it will descend in order. When it gets to the bottom of the list, it will start at the top again. This is repeated for every topic for this user. This is controlled by the priorities set on the campaign level and tactic level. This is the simplest case.

If there is a tie in the score, then the oldest content is shown first.


#### Required Algorithms {#required-algorithms}


##### View Target {#view-target}

In some cases there is a need to show tactics in a sequential order to users. This can be done using start/end dates in tactics, however we can also serve this to a user once they have viewed the first one. Integration with our metrics provider will be required to provide an accurate view number, as a result, the queue generation will be slightly out of step with the actual view numbers.

This may not be in the first iteration since mixpanel will have to be integrated with at the backend. 


#### Algorithm Ideas {#algorithm-ideas}


##### Serve Target {#serve-target}

Related to View Target could be something called Serve Target where instead of guaranteeing that the user has seen a tactic, we can serve the next one to a user once the first has been served. 

If a tactic has this attribute, each user would essentially only have one tactic available to serve at a given time, so the priority of the visible tactic would be used to determine placement.


##### Expire On

This one is combined with Serve Target or View Target to remove a tactic once it has been viewed X times. This works by setting the end date of the tactic to now. 


##### Tactic Chaining {#tactic-chaining}

This would track whether a tactic has been served. This would allow serving in a specific order so a user could scroll down and see content1 then content2 then content3 and so on. The order would be decided based on the first tactic, when the first tactic of a chain like this is shown, then rest are shown in order without checking priority.

This could be combined Always Here to start a chain at a specific point or Always On Top to always start at the top.


##### Always On Top {#always-on-top}

This can only be set for one tactic at a time for a given targeted group. The level priority is still used in this case, if the most specific match has a tactic set to always on top, that tactic will always appear first. This essentially acts as a flag, if view target or serve target is set for this tactic, it drops back to normal priority after the number defined, otherwise, it will stay on top until the tactic or campaign ends.

This flag overrides Always Here.


##### Always Here {#always-here}

Define a position for this tactic or campaign to always be in if any of the profession targets are hit. This is not the absolute number of the item in the feed, but rather the position in the sponsored content queue. For example, putting a campaign in position 3 means that the third piece of sponsored content will always be one from this campaign. If View Target is not selected, then Serve Target is used by default to ensure rotation through the campaign tactics. If the position falls off the end ( position 10 of a 5 item queue ) it defaults to the end position.


#### Requirements:



*   Scoring is configurable per campaign and per tactic and is cumulative.
*   The ordering for a specific user cannot be guaranteed directly, this is because the level priority, campaign priority, and tactic priority are all taken into account. This is fudgable with things like Always Here, or Always On Top. 




## Appendix A - As Built

There are always modifications that come when something is actually built. Instead of modifying the primary document continuously, any changes will be added here:


#### Feed Placement Algorithms:

After some back and forth, it was decided that the initial build will not have any algorithms built in. Instead, we will rely only on the scoring algorithm with the idea that simpler is better in order to try to keep things slim and add things that are requested later.


#### Targeting

An additional potential wrinkle was adding practice areas, however, while we show these separately in the UI, they are treated the same way as sub-specialties. They will match slightly differently, however this is a change in field target. 


#### Scoring {#scoring}

While the design calls for a score of 1-3 for 3 different areas for a combined max score of 9 and a min score of 3, the UI allows for the campaign score and tactic score to be any positive integer. While this potentially unbalances the scores, it does BD more room to tweak scores. The backend will not enforce a maximum integer here. 
