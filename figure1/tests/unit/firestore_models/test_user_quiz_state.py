import uuid
import time
from figure1.common.models.firebase import QuizStateModel, QuizContentItem, QuizOption, FirestoreCaseProgressState
from figure1.common.types import ContentType, MediaModel, MediaType

content_uuid_1 = uuid.uuid4()
content_uuid_2 = uuid.uuid4()
case_uuid = uuid.uuid4()


def generate_quiz_document(answer) -> QuizStateModel:
    media_1 = dict(url='https://example.com',
                   display_order=0,
                   media_uuid=uuid.uuid4(),
                   content_uuid=content_uuid_1,
                   type=MediaType.IMAGE,
                   width=40,
                   height=199)
    media_2 = dict(url='https://example.com',
                   display_order=1,
                   media_uuid=uuid.uuid4(),
                   content_uuid=content_uuid_1,
                   type=MediaType.IMAGE,
                   width=40,
                   height=199)

    option_uuid_1 = dict(question_option_uuid=uuid.uuid4(), is_answer=True, display_order=0)
    option_uuid_2 = dict(question_option_uuid=uuid.uuid4(), is_answer=False, display_order=1)
    option_uuid_3 = dict(question_option_uuid=uuid.uuid4(), is_answer=True, display_order=2)
    userVote = option_uuid_2.get('question_option_uuid')
    content_1 = dict(title='Title1',
                     caption='Caption1',
                     content_uuid=content_uuid_1,
                     content_type='QUIZ_SERIES',
                     display_order=0,
                     options=[QuizOption.parse_obj(option_uuid_1),
                              QuizOption.parse_obj(option_uuid_2),
                              QuizOption.parse_obj(option_uuid_3)],
                     media=[MediaModel.parse_obj(media_1),
                            MediaModel.parse_obj(media_2)])
    content_2 = dict(title='Title2',
                     caption='Caption2',
                     content_uuid=content_uuid_2,
                     content_type=ContentType.QUIZ_SERIES,
                     display_order=1,

                     options=[QuizOption.parse_obj(option_uuid_1),
                              QuizOption.parse_obj(option_uuid_2),
                              QuizOption.parse_obj(option_uuid_3)],
                     media=[MediaModel.parse_obj(media_1),
                            MediaModel.parse_obj(media_2)])
    if answer == 1:
        content_1.update({'userVote': userVote})
    else:
        content_2.update({'userVote': userVote})
        content_1.pop('options')

    return QuizStateModel(content_items=[QuizContentItem.parse_obj(content_1),
                                         QuizContentItem.parse_obj(content_2)])


def test_quiz_series_model_answer_one() -> FirestoreCaseProgressState:
    """
    Test the model that syncs to firestore.
    1. Ensure that uuids are converted to strings
    2. Ensure that either enums or the name for content-type can be used
    3. Ensure that all required fields are created

    :return:
    """

    quiz = generate_quiz_document(answer=1)

    state_object = dict(case_uuid=case_uuid, user_uid="test_user_uid", content=quiz)

    fs_state = FirestoreCaseProgressState.parse_obj(state_object)

    fs_doc = fs_state.generate_firestore_document()
    assert len(fs_doc.keys()) == 2
    return fs_state


def test_quiz_series_model_answer_two() -> FirestoreCaseProgressState:
    quiz = generate_quiz_document(answer=2)

    state_object = dict(case_uuid=case_uuid, user_uid="test_user_uid", content=quiz)

    fs_state = FirestoreCaseProgressState.parse_obj(state_object)

    fs_doc = fs_state.generate_firestore_document()
    assert len(fs_doc.keys()) == 2
    return fs_state


def test_firestore_state():
    sync_fs = test_quiz_series_model_answer_one()
    sync_fs.firestore_write()
    fs_doc = sync_fs.firestore_get()
    assert fs_doc is not None
    assert fs_doc.to_dict() == sync_fs.generate_firestore_document()

    sync_fs_ans_2 = test_quiz_series_model_answer_two()
    sync_fs_ans_2.firestore_write()
    fs_doc_2 = sync_fs_ans_2.firestore_get()
    assert fs_doc_2 is not None
    fs_dict = fs_doc_2.to_dict()
    assert 'options' in fs_dict[str(content_uuid_1)]

    assert fs_dict[str(content_uuid_1)]['userVote'] is not None
    assert fs_dict[str(content_uuid_2)]['userVote'] is not None
