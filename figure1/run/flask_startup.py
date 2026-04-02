import logging
import os
import json
# noinspection PyUnresolvedReferences
import figure1.configuration.log_settings
from time import time
from flask import Flask, g, Response, request, jsonify, abort
from flask_jwt_extended import JWTManager

from flasgger import Swagger

from figure1.common.models.db import BackendToken
from figure1.common.token_rotator import run_token_rotator, validate_token
from figure1.configuration import FlaskSettings
from figure1.core import configure_environment, remove_scoped_session
from figure1.admin import *
from figure1.explorer import *
from figure1.pro import *
from figure1.tools import *
from figure1.exceptions import general_exception_endpoints


def health():
    return jsonify('OK'), 200


def token_health():
    t = BackendToken.get_text_token()
    if validate_token(_token=t):
        return jsonify('OK'), 200
    else:
        return abort(500, 'Current token is invalid')


def create_app(settings: FlaskSettings):
    """
    Creates the backend flask app and registers all blueprints
    :return: None
    """
    # create the app
    flask_app = Flask(__name__)

    flask_app.config['MAX_CONTENT_LENGTH'] = settings.upload_max_content_length
    flask_app.config['UPLOAD_FOLDER'] = settings.upload_temp_dir
    flask_app.config['JWT_SECRET_KEY'] = settings.jwt_secret_key
    flask_app.config['JWT_AUTH_URL_RULE'] = settings.jwt_auth_url_rule
    flask_app.config['SWAGGER'] = {
        'specs': [
            {
                "endpoint": "apispec_1",
                "route": "/swagger/v1/apispec_1.json",
                "rule_filter": lambda rule: True,  # all in
                "model_filter": lambda tag: True,  # all in
            }
        ],
        "static_url_path": "/swagger/v1/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/swagger/v1/apidocs"
    }

    if settings.flask_mode == "testing":
        flask_app.config['TESTING'] = True

    # register general exception handlers
    flask_app.register_blueprint(general_exception_endpoints)

    # Register url endpoints
    flask_app.register_blueprint(pro_tools_endpoints, url_prefix='/tools/v1')
    flask_app.register_blueprint(admin_moderation_tagging_endpoint, url_prefix='/admin/v1')
    flask_app.register_blueprint(admin_campaign_endpoint, url_prefix='/admin/v1')
    flask_app.register_blueprint(admin_campaign_case_endpoint, url_prefix='/admin/v1')
    flask_app.register_blueprint(admin_migrate_cases_endpoint, url_prefix='/admin/v1')
    flask_app.register_blueprint(admin_migrate_users_endpoint, url_prefix='/admin/v1')
    flask_app.register_blueprint(admin_reference_data_endpoint, url_prefix='/admin/v1')
    flask_app.register_blueprint(admin_moderation_cases_endpoint, url_prefix='/admin/v1')
    flask_app.register_blueprint(admin_moderation_comments_endpoint, url_prefix='/admin/v1')
    flask_app.register_blueprint(admin_tools_endpoint, url_prefix='/admin/v1')
    flask_app.register_blueprint(admin_verification_endpoint, url_prefix='/admin/v1')
    flask_app.register_blueprint(iterable_admin_api, url_prefix='/admin/v1/')
    flask_app.register_blueprint(admin_elasticsearch_endpoint, url_prefix='/admin/v1/elasticsearch')
    flask_app.register_blueprint(admin_api_auth, url_prefix='/_swagger/v1')
    flask_app.register_blueprint(explorer_search, url_prefix='/explorer/v1')
    flask_app.register_blueprint(explorer_cases, url_prefix='/explorer/v1')
    flask_app.register_blueprint(pro_cases_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_feeds_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_topics_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_users_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_groups_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_verification_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_notifications_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_cases_quiz_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_cases_upload_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_cme_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_comments_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_mentions_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_search_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_tracking_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(api_endpoint, url_prefix='/api/v1')
    flask_app.register_blueprint(pro_legacy_endpoint, url_prefix='/pro/v1')
    flask_app.register_blueprint(pro_case_cme_endpoints, url_prefix='/pro/v1')

    # Create endpoint for healthchecks
    flask_app.add_url_rule('/health', 'health', health)
    flask_app.add_url_rule('/health/token', 'token_health', token_health)

    swag = Swagger(flask_app)
    return flask_app


def log_startup(app: Flask):
    debug = app.debug
    testing = app.config['TESTING']
    prop_ex = app.config['PROPAGATE_EXCEPTIONS']
    logger = logging.getLogger('figure1.startup')
    logger.info("flask started with debug %s, testing %s, propagate %s, log level %s", debug, testing, prop_ex, logging.getLevelName(logger.getEffectiveLevel()))


def initialize_app():
    os.environ['LC_ALL'] = 'C.UTF-8'
    os.environ['LANG'] = 'C.UTF-8'
    configure_environment()
    settings = FlaskSettings()
    app = create_app(settings=settings)
    JWTManager(app)

    log_startup(app)

    # for debugging
    if os.getenv("DEBUG_ENV") == "true":
        safe_env = {}
        for k, v in os.environ.items():
            if any(x in k for x in ["KEY", "SECRET", "PASS"]):
                if v and len(v) > 5:
                    safe_env[k] = v[:5] + "..." + "*" * (len(v) - 8) + v[-3:]
                else:
                    safe_env[k] = "***hidden***"
            else:
                safe_env[k] = v
        app.logger.info("Loaded environment variables: %s", json.dumps(safe_env, indent=2))

    app.logger = logging.getLogger('gunicorn') # type: ignore

    if settings.read_only_dev_mode:
        print("using read only dev mode")
        @app.before_request
        def intercept_post_requests():
            exceptions = ['/pro/v1/feeds/', '/pro/v1/user/auth_check', '/tools/rotate_token']
            # /pro/v1/feeds/<userid>, /pro/v1/user/auth_check
            if request.method != "GET" and not any(
                    request.path.startswith(e) for e in exceptions
            ):
                app.logger.info(f"Intercepted Write Operation -> {request.path}")
                print(f"Intercepted Write Operation -> {request.path}")
                return jsonify({"error": "POST requests are not allowed"}), 405
            return None

    @app.teardown_request
    def teardown_session(f: Response):
        remove_scoped_session()

    return app

app = initialize_app()
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=30000, debug=True)
