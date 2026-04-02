from .settings import FlaskSettings, \
    ElasticSearchSettings, \
    AppSettings, \
    TestSettings, \
    FirebaseEnvSettings
from .log_settings import configure_log_settings

flask_settings = FlaskSettings(jwt_secret_key='test1234')
app_settings = AppSettings()
es_settings = ElasticSearchSettings()
test_settings = TestSettings()
configure_log_settings(app_settings=app_settings)
