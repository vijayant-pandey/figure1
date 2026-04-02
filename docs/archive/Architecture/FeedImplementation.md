### Feed Implementation


#### Executive Summary

In Pro, feeds are the central point around which all of our content is surfaced. We have three general classifications of feeds: 

The Recommended For You( RFY ) feed is generated and controlled by the end user by adding or modifying interests,

The Everything feed is a feed that is sorted by created date, but has no other default filters, 

The Topic feeds are all feeds that can be subscribed to or unsubscribed from by a user.

 \
The RFY feed and the Everything feed are not unsubscribable, that is, all users are subscribed to both of them by default and cannot unsubscribe from them.

Sponsored content will be injected into the feeds as well, however this is not yet settled so for the moment is out of scope.


#### Technical Summary

On a technical level, each of the topic feeds and the everything feed is in a dedicated index in elasticsearch, the RFY feed is not in a dedicated index, but is generated from the everything feed and subsequently filtered using the users interests. Practically speaking, this means that cases which are newly approved need to be indexed into the everything feed where they will propagate into the rest of the topic feeds. 

The reasoning behind this decision is to spread the query load between different indexes as much as possible, however strictly speaking, topic indexes could be run as filters in the same way as RFY feeds are. The tradeoff is the potential for hot nodes/indexes, however it would simplify the re-indexing implementation.

The page size for all feeds is currently 10 items. This may be modified in the future, but should not generally affect anything that follows here.

All feeds have a generate call and an update call. The generate call resets the feed back to the beginning, while the update call gets the next group of documents.

This document covers the implementation, not all of the options described are available through the UI. This is noted throughout this document.


#### Recommended For You

This feed is created through a series of filters on the everything feed. Right now, the interests available are only specialties, however this is likely the change in the near future. The sorting here is by relevance, the sorting order for this and any other feed is configurable, but this is not available on the frontend currently. 

When the user refreshes this feed by pulling down, it returns to the top. Similarly, when a user modifies the interests, this feed should re-generate. Only interests are currently taken into account for this feed. When a user is created, if no interests are selected, then the users specialties/subspecialties are copied into interests and those are used. Importantly, this means that modifying a user's specialties/subspecialties does not affect the RFY feed after the user is created. 

The RFY feed cannot be unsubscribed from.


#### Everything Feed

This feed is the same for everyone, it contains all of the approved cases currently available in figure1, though the length is capped at 10000 for performance reasons. By default, this feed is sorted by created date, this is modifiable though it is not currently exposed in the UI. 

Similar to the RFY feed, the Everything feed cannot be unsubscribed from.


#### Topic Feeds

All of the feeds that are not Everything or RFY feeds are Topic feeds. Right now, these feeds are collections of sub-specialties that are created by filtering from the everything feed. These feeds sort by relevance generally, like the other feeds, this is customizable, though not currently exposed. 

The topic feeds can be exposed which means they are subscribable by users or they can be hidden which means they are not exposed as subscribable. The default state for feeds is to be visible to end users.

When a user subscribes to a feed, the first 10 items are generated and written to the UserFeedDB in firestore along with the metadata describing this feed. This is an area for optimization as this process is not immediate. 

While working through this, some additional functionality was added in to make development easier and work through some issues. These features are not exposed to either end users or to administrators at this point, however the implementation will stay in place and should be exposed to administrative users as it offers a substantial degree of customization. 

The available customizations are as follows:


##### Expiration Query

This property is an arbitrary elasticsearch query, any items that do not match this query are dropped from the feed. The most obvious use case for this is something like a New Cases feed which drops cases after a certain time from creation date. Though the most obvious use case for this is a time based query, the query used is arbitrary.


##### Filter Query

This property is also an arbitrary elasticsearch query, however instead of removing items from a feed, this query selects items to be in a feed. Because of the way that feeds are generated, this is a one-way operation - that is, items added to a feed by this query will not be removed if they no longer match. 


##### Sort

While topic feeds can take sort parameters from the UI, it is also possible to set the default sort fields for each individual feed. These sort fields are overridden if there are options passed in at generation time.
