class PromotionTestModels:

    @staticmethod
    def create_channel():
        return {
            'channel_name': 'Twitter Test'
        }

    @staticmethod
    def create_promotion(channel_uuid, promotion_name="Test Promotion"):
        return {
            'channel_uuid': channel_uuid,
            'promotion_name': promotion_name
        }

    @staticmethod
    def case_model(promotion_uuid, case_uuid):
        return {
            'promotion_uuid': promotion_uuid,
            'case_id': case_uuid
        }


class ElasticSearchModels:

    @staticmethod
    def one_case():
        return {
            'image_url': "",
            'caseUuid': "",
            'legacyId': "",
            'caption': "",
            'userUuid': "",
            'title': "",
            'likes': "",
            'follows': "",
            'username': "",
            'email': "",
            'verified': "",
            'countryUuid': "",
            'countryName': "",
            'countryCode': "",
            'countryAlpha3': "",
            'typeUuid': "",
            'label': "",
            'caseState': "",
            'taggingState': "",
            'mesh_terms': [],
            'mesh_terms_text': [],
            'comment_meta': [
                {
                    'typeUuid': "",
                    'total_count': "",
                    'unique_user_count': ""
                }
            ],
            'comments': [
                {
                    'language': "",
                    'likes': "",
                    'parentId': "",
                    'acceptedAnswer': "",
                    'username': "",
                    'email': "",
                    'verified': "",
                    'typeUuid': "",
                    'label': "",
                    'commentUuid': "",
                    'userUuid': "",
                    'caseUuid': "",
                    'text': ""
                }
            ]
        }
