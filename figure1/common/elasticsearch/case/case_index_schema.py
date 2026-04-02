class CaseMapSchema:
    case_index_settings = {
        "index": {
            "number_of_replicas": 0
        }
    }
    date_key_format = {
        "type": "date",
        "format": "yyyy-MM-dd HH:mm:ss.SSSSSSXXX||yyyy-MM-dd HH:mm:ssXXX||date_optional_time"
    }
    keyword_format = {"type": "keyword"}
    text_format = {"type": "text"}
    integer_format = {"type": "integer"}
    boolean_format = {"type": "boolean"}

    campaign_settings = {
        "type": "nested",
        "properties": {
            "campaignUuid": keyword_format,
            "campaignState": keyword_format,
            "startDate": date_key_format,
            "endDate": date_key_format,
            "professionTargets": keyword_format,
            "specialtyTargets": keyword_format,
            "subSpecialtyTargets": keyword_format,
            "treeTargets": keyword_format,
            "countryTargets": keyword_format,
            "languageTargets": keyword_format,
            "verificationTarget": boolean_format,
            "isSponsored": boolean_format,
            "tacticPriority": integer_format,
            "campaignPriority": integer_format,
            "tacticName": text_format,
        }
    }
    content_sponsoredContent = {
        "type": "nested",
        "properties": {
            "sponsoredText": text_format,
            "disclosureText": text_format,
            "jobCode": text_format,
        }
    }
    content_questionOptions = {
        "type": "nested",
        "properties": {
            "questionOptionUuid": keyword_format,
            "displayOrder": integer_format,
            "text": {
                "type": "text",
                "copy_to": "contentSearch"
            },
            "votes": integer_format,
            "isAnswer": boolean_format,
        }
    }
    content_features = {
        "type": "nested",
        "properties": {
            "commentBarEnabled": boolean_format,
            "commentsEnabled": boolean_format,
            "reactionsEnabled": boolean_format,
            "reportEnabled": boolean_format,
            "requireAnswer": boolean_format,
            "shareEnabled": boolean_format,
            "showComments": boolean_format,
            "showViews": boolean_format,
        }
    }
    content_updates = {
        "type": "nested",
        "properties": {
            "updateUuid": keyword_format,
            "createdAt": date_key_format,
            "text": {
                "type": "text",
                "copy_to": "contentSearch"
            },
            "updateType": keyword_format,
        }
    }

    content_items = {
        "type": "nested",
        "properties": {
            "title": {
                "type": "text",
                "copy_to": "contentSearch"
            },
            "caption": {
                "type": "text",
                "copy_to": "contentSearch"
            },
            "contentUuid": keyword_format,
            "commentCount": integer_format,
            "contentType": keyword_format,
            "buttonText": text_format,
            "buttonUrl": text_format,
            "externalLinkText": text_format,
            "externalLinkUrl": text_format,
            "colour": text_format,
            "heading": {
                "type": "text",
                "copy_to": "contentSearch"
            },
            "feedCardTitle": {
                "type": "text",
                "copy_to": "contentSearch"
            },
            "feedCardLabel": {
                "type": "text",
                "copy_to": "contentSearch"
            },
            "questionAnswerDetails": {
                "type": "text",
                "copy_to": "contentSearch"
            },
            "displayOrder": integer_format,
            "updates": content_updates,
            "features": content_features,
            "sponsoredContent": content_sponsoredContent,
            "questionOptions": content_questionOptions,
        }
    }

    moderation_edit = {
        "type": "nested",
        "properties": {
            "editUuid": keyword_format,
            "createdAt": date_key_format,
            "updatedAt": date_key_format,
            "mediaUuid": keyword_format,
            "contentUuid": keyword_format,
            "moderatorUuid": keyword_format,
            "moderatorUsername": text_format,
            "editType": keyword_format,
            "caption": text_format,
            "title": text_format,
            "language": text_format,
            "diagnosis": text_format,
            "filename": keyword_format,
            "url": keyword_format
        }
    }
    moderation_notes = {
        "type": "nested",
        "properties": {
            "noteCreated": date_key_format,
            "noteUpdated": date_key_format,
            "noteUuid": keyword_format,
            "noteText": text_format,
            "noteAuthorUuid": keyword_format,
            "noteAuthorUsername": text_format
        }
    }

    case_authors = {
        "type": "nested",
        "properties": {
            "userUuid": keyword_format,
            "specialtyUuid": keyword_format,
            "username": text_format,
            "firstName": text_format,
            "lastName": text_format,
            "name": text_format,
            "email": text_format,
            "verificationStatus": keyword_format,
            "lastSeen": date_key_format
        }
    }

    case_media = {
        "type": "nested",
        "properties": {
            "mediaUuid": keyword_format,
            "type": keyword_format,
            "url": keyword_format,
            "width": integer_format,
            "height": integer_format,
            "displayOrder": integer_format
        }
    }

    case_comments = {
        "type": "nested",
        "properties": {
            "commentUuid": keyword_format,
            "authorUuid": keyword_format,
            "contentUuid": keyword_format,
            "createdAt": date_key_format,
            "updatedAt": date_key_format,
            "text": {
                "type": "text",
                "copy_to": "commentSearch"
            }
        }
    }

    case_feed_card_media = {
        "type": "nested",
        "properties": {
            "mediaUuid": keyword_format,
            "type": keyword_format,
            "url": keyword_format,
            "width": integer_format,
            "height": integer_format,
            "displayOrder": integer_format
        }
    }

    case_promotions = {
        "type": "nested",
        "properties": {
            "promotion_uuid": keyword_format,
            "promotion_publish_date": date_key_format,
            "promotion_name": text_format,
            "promotion_notes": text_format,
            "channel_uuid": keyword_format,
            "case_notes": text_format,
            "case_alternate_description": text_format,
            "case_alternate_title": text_format,
            "case_alternate_caption": text_format
        }
    }

    case_map_data = {
        "settings": case_index_settings,
        "mappings": {
            "properties": {
                "createdAt": date_key_format,
                "updatedAt": date_key_format,
                "publishedAt": date_key_format,
                "specialtyUuids": keyword_format,
                "specialtyNames": keyword_format,
                "caseUuid": keyword_format,
                "caseState": keyword_format,
                "caseType": keyword_format,
                "caseClassification": keyword_format,
                "commentCount": integer_format,
                "labels": keyword_format,
                "commentSearch": text_format,
                "contentSearch": text_format,
                "feedCardType": keyword_format,
                "moderationEdit": moderation_edit,
                "isSponsored": boolean_format,
                "moderationNotes": moderation_notes,
                "campaignSettings": campaign_settings,
                "comments": case_comments,
                "contentItems": content_items,
                "authorUid": keyword_format,
                "authors": case_authors,
                "media": case_media,
                "taggingState": keyword_format,
                "meshTerms": {
                    "type": "keyword",
                    "fields": {
                        "text": {
                            "type": "text",
                            "analyzer": "english"
                        }
                    }
                },
                "caption": {
                    "type": "text",
                    "analyzer": "english"
                },
                "title": {
                    "type": "text",
                    "analyzer": "english"
                },
                "likes": integer_format,
                "follows": integer_format,
                "userSaved": keyword_format,
                "trendScore": integer_format,
                "reactions": {
                    "type": "nested",
                    "properties": {
                        "agree": keyword_format,
                        "clinicallyUseful": keyword_format,
                        "informative": keyword_format,
                    }
                },
                "latestReactions": {
                    "type": "nested",
                    "properties": {
                        "userUuid": keyword_format,
                        "date": date_key_format
                    }
                },
                "isPagingCase": boolean_format,
                "feedCardMedia": case_feed_card_media,
                "promotions": case_promotions,
                "groupUuid": keyword_format,
                "diagnoses": content_updates,
                "hasDiagnosis": boolean_format,
                "isCaseCme": boolean_format,
                "isAnonymous": boolean_format,
                "hasAcceptedAnswer": boolean_format,
                "requestHelp": boolean_format,
            }
        }
    }
