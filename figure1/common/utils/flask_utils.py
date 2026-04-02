from celery.canvas import Signature
from flask import jsonify


def execute_on_return(task, synchronous=False, response=None):
    if response is None:
        response = {}
    if isinstance(task, Signature):
        if synchronous:
            task.apply()
            return jsonify(response), 200
        else:
            task.apply_async()
            return jsonify(response), 200
    else:
        return jsonify(response), 200
