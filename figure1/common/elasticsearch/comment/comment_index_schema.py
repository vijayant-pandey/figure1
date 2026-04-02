class CommentMapSchema:
    comment_map_data = {
        "mappings": {
            "properties": {
                "createdAt": {
                    "type": "date",
                    "format": "yyyy-MM-dd HH:mm:ss.SSSSSSXXX||yyyy-MM-dd HH:mm:ssXXX||date_optional_time"
                },
                "updatedAt": {
                    "type": "date",
                    "format": "yyyy-MM-dd HH:mm:ss.SSSSSSXXX||yyyy-MM-dd HH:mm:ssXXX||date_optional_time"
                },
                "authorUuid": {
                    "type": "keyword"
                },
                "authorAvatar": {
                    "type": "text"
                },
                "authorMetadata": {
                    "type": "nested",
                    "properties": {
                        "commentsAll": {
                            "type": "integer"
                        },
                        "commentsRejected": {
                            "type": "integer"
                        },
                    }
                },
                "authorProfessionName": {
                    "type": "text"
                },
                "authorUsername": {
                    "type": "text"
                },
                "case": {
                    "type": "nested",
                    "properties": {
                        "caption": {
                            "type": "text"
                        },
                        "mediaThumbnailUrl": {
                            "type": "text"
                        },
                        "title": {
                            "type": "text"
                        },
                        "groupUuid": {
                            "type": "keyword"
                        },
                        "deletedAt": {
                            "type": "date",
                            "format": "yyyy-MM-dd HH:mm:ss.SSSSSSXXX||yyyy-MM-dd HH:mm:ssXXX||date_optional_time"
                        },
                        "caseUuid": {
                            "type": "keyword"
                        },
                    }
                },
                "commentUuid": {
                    "type": "keyword"
                },
                "contentUuid": {
                    "type": "keyword"
                },
                "flags": {
                    "type": "nested",
                    "properties": {
                        "moderatorUuid": {
                            "type": "keyword"
                        },
                        "moderatorUsername": {
                            "type": "text"
                        },
                        "moderatorName": {
                            "type": "text"
                        },
                        "flaggedAt": {
                            "type": "date",
                            "format": "yyyy-MM-dd HH:mm:ss.SSSSSSXXX||yyyy-MM-dd HH:mm:ssXXX||date_optional_time"
                        },
                    }
                },
                "language": {
                    "type": "text"
                },
                "path": {
                    "type": "text"
                },
                "replyable": {
                    "type": "boolean"
                },
                "isAcceptedAnswer": {
                    "type": "boolean"
                },
                "isAnonymous": {
                    "type": "boolean"
                },
                "isCaseAnonymous": {
                    "type": "boolean"
                },
                "isCaseAuthor": {
                    "type": "boolean"
                },
                "moderatorReviewed": {
                    "type": "boolean"
                },
                "moderatorReviewStatus": {
                    "type": "keyword"
                },
                "reports": {
                    "type": "nested",
                    "properties": {
                        "reporterUuid": {
                            "type": "keyword"
                        },
                        "reporterUsername": {
                            "type": "text"
                        },
                        "reportedAt": {
                            "type": "date",
                            "format": "yyyy-MM-dd HH:mm:ss.SSSSSSXXX||yyyy-MM-dd HH:mm:ssXXX||date_optional_time"
                        },
                        "reportReason": {
                            "type": "text"
                        },
                        "text": {
                            "type": "text"
                        },
                    }
                },
                "state": {
                    "type": "keyword"
                },
                "text": {
                    "type": "text"
                },
            }
        }
    }
