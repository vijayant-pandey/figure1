import multiprocessing

forwarded_allow_ips = '*'
bind = '0.0.0.0:30000'
worker_class = 'gthread'
workers = (multiprocessing.cpu_count() * 2) + 1
threads = workers

log_file = "-"

timeout = 120

wsgi_app = 'figure1.run:initialize_app()'
