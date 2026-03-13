"""Twitter API constants: bearer token, GraphQL query IDs, feature flags."""

# Public bearer token used by Twitter's web client (not a secret)
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# GraphQL operation query IDs (from x.com JS bundles)
QUERY_IDS = {
    "Retweeters": "qVWT1Tn1FiklyVDqYiOhLg",
    "CreateList": "nHFMQuE0r6yVEGmPSSbDdg",
    "ListAddMember": "sw71TVciw0CoWPcFfIhrnA",
    "ListRemoveMember": "cvl5jMbF1DqPRJalJTkNzA",
    "UserByScreenName": "xmU6X_CKVnQ5lSrCbAmJsg",
    "HomeTimeline": "HJFjzBgCs16TqxewQOeLNg",
    "UserTweets": "E3opETHurmVJflFsUBVuUQ",
    "Bookmarks": "j5KExFXtSqHHgK3MBfOuBw",
    "SearchTimeline": "gkjsKepM6gl_HmFWoWKfgg",
    "TweetDetail": "nBS-WpgA6ZG0CyNHD517JQ",
    "Favorites": "eSSNbhECHHWWALkkQq-YTA",
    "ListMembers": "BQp2IEYkgxuSxqbTAr1e1g",
    "CreateBookmark": "aoDbu3RHznuiSkQ9aNM67Q",
}

GRAPHQL_BASE = "https://x.com/i/api/graphql"

# Feature flags sent with most GraphQL requests
TIMELINE_FEATURES = {
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

USER_FEATURES = {
    "hidden_profile_subscriptions_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}
