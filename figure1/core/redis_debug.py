"""
Redis Connection Debugging Module

This module provides comprehensive debugging tools for Redis connections
used by Celery workers. It includes connection testing, health checks,
and detailed logging for troubleshooting Redis connectivity issues.
"""

import logging
import time
import socket
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
import redis
from redis.sentinel import Sentinel

logger = logging.getLogger(__name__)


class RedisConnectionDebugger:
    """Debug Redis connections and provide detailed diagnostics."""
    
    def __init__(self, redis_url: str, sentinel_enabled: bool = False):
        self.redis_url = redis_url
        self.sentinel_enabled = sentinel_enabled
        self.logger = logging.getLogger(f"{__name__}.RedisConnectionDebugger")
        
    def parse_redis_url(self) -> Dict[str, Any]:
        """Parse Redis URL and return connection details."""
        self.logger.debug(f"Parsing Redis URL: {self.redis_url}")
        
        if self.sentinel_enabled:
            # Handle sentinel URLs
            urls = self.redis_url.split(';')
            parsed_urls = []
            for url in urls:
                parsed = urlparse(url.strip())
                parsed_urls.append({
                    'scheme': parsed.scheme,
                    'hostname': parsed.hostname,
                    'port': parsed.port or 26379,
                    'path': parsed.path,
                    'username': parsed.username,
                    'password': parsed.password,
                    'netloc': parsed.netloc
                })
            return {'type': 'sentinel', 'urls': parsed_urls}
        else:
            # Handle single Redis URL
            parsed = urlparse(self.redis_url)
            return {
                'type': 'redis',
                'scheme': parsed.scheme,
                'hostname': parsed.hostname,
                'port': parsed.port or 6379,
                'path': parsed.path,
                'username': parsed.username,
                'password': parsed.password,
                'netloc': parsed.netloc
            }
    
    def test_network_connectivity(self, hostname: str, port: int, timeout: int = 5) -> Dict[str, Any]:
        """Test basic network connectivity to Redis host."""
        self.logger.debug(f"Testing network connectivity to {hostname}:{port}")
        
        result = {
            'hostname': hostname,
            'port': port,
            'reachable': False,
            'error': None,
            'response_time': None
        }
        
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((hostname, port))
            sock.close()
            
            result['reachable'] = True
            result['response_time'] = time.time() - start_time
            self.logger.debug(f"Network connectivity test passed: {hostname}:{port} (response time: {result['response_time']:.3f}s)")
            
        except socket.timeout:
            result['error'] = f"Connection timeout after {timeout}s"
            self.logger.error(f"Network connectivity test failed: {hostname}:{port} - {result['error']}")
        except socket.gaierror as e:
            result['error'] = f"DNS resolution failed: {e}"
            self.logger.error(f"Network connectivity test failed: {hostname}:{port} - {result['error']}")
        except ConnectionRefusedError:
            result['error'] = "Connection refused"
            self.logger.error(f"Network connectivity test failed: {hostname}:{port} - {result['error']}")
        except Exception as e:
            result['error'] = f"Unexpected error: {e}"
            self.logger.error(f"Network connectivity test failed: {hostname}:{port} - {result['error']}")
        
        return result
    
    def test_redis_connection(self, connection_params: Dict[str, Any]) -> Dict[str, Any]:
        """Test Redis connection with detailed diagnostics."""
        self.logger.debug(f"Testing Redis connection with params: {connection_params}")
        
        result = {
            'success': False,
            'error': None,
            'redis_info': None,
            'response_time': None,
            'connection_params': connection_params
        }
        
        try:
            start_time = time.time()
            
            if connection_params.get('type') == 'sentinel':
                # Test sentinel connection
                sentinel_hosts = [(url['hostname'], url['port']) for url in connection_params['urls']]
                self.logger.debug(f"Testing sentinel connection to hosts: {sentinel_hosts}")
                
                sentinel = Sentinel(sentinel_hosts, socket_timeout=5)
                master = sentinel.master_for('redismaster', socket_timeout=5)
                
                # Test basic Redis operations
                master.ping()
                info = master.info()
                
                result['success'] = True
                result['redis_info'] = info
                result['response_time'] = time.time() - start_time
                
                self.logger.debug(f"Sentinel Redis connection test passed (response time: {result['response_time']:.3f}s)")
                
            else:
                # Test direct Redis connection
                redis_client = redis.Redis(
                    host=connection_params['hostname'],
                    port=connection_params['port'],
                    password=connection_params.get('password'),
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                
                # Test basic Redis operations
                redis_client.ping()
                info = redis_client.info()
                
                result['success'] = True
                result['redis_info'] = info
                result['response_time'] = time.time() - start_time
                
                self.logger.debug(f"Direct Redis connection test passed (response time: {result['response_time']:.3f}s)")
                
        except redis.ConnectionError as e:
            result['error'] = f"Redis connection error: {e}"
            self.logger.error(f"Redis connection test failed: {result['error']}")
        except redis.TimeoutError as e:
            result['error'] = f"Redis timeout error: {e}"
            self.logger.error(f"Redis connection test failed: {result['error']}")
        except redis.AuthenticationError as e:
            result['error'] = f"Redis authentication error: {e}"
            self.logger.error(f"Redis connection test failed: {result['error']}")
        except Exception as e:
            result['error'] = f"Unexpected Redis error: {e}"
            self.logger.error(f"Redis connection test failed: {result['error']}")
        
        return result
    
    def run_comprehensive_diagnostics(self) -> Dict[str, Any]:
        """Run comprehensive Redis diagnostics."""
        self.logger.info("=== STARTING COMPREHENSIVE REDIS DIAGNOSTICS ===")
        
        diagnostics = {
            'timestamp': time.time(),
            'redis_url': self.redis_url,
            'sentinel_enabled': self.sentinel_enabled,
            'parsed_url': None,
            'network_tests': [],
            'redis_tests': [],
            'summary': {}
        }
        
        # Parse Redis URL
        try:
            diagnostics['parsed_url'] = self.parse_redis_url()
            self.logger.debug(f"Parsed URL: {diagnostics['parsed_url']}")
        except Exception as e:
            self.logger.error(f"Failed to parse Redis URL: {e}")
            diagnostics['summary']['url_parsing_error'] = str(e)
            return diagnostics
        
        # Test network connectivity
        if diagnostics['parsed_url']['type'] == 'sentinel':
            for url_info in diagnostics['parsed_url']['urls']:
                network_test = self.test_network_connectivity(url_info['hostname'], url_info['port'])
                diagnostics['network_tests'].append(network_test)
        else:
            url_info = diagnostics['parsed_url']
            network_test = self.test_network_connectivity(url_info['hostname'], url_info['port'])
            diagnostics['network_tests'].append(network_test)
        
        # Test Redis connections
        redis_test = self.test_redis_connection(diagnostics['parsed_url'])
        diagnostics['redis_tests'].append(redis_test)
        
        # Generate summary
        diagnostics['summary'] = self._generate_summary(diagnostics)
        
        self.logger.info("=== COMPREHENSIVE REDIS DIAGNOSTICS COMPLETE ===")
        self.logger.info(f"Summary: {diagnostics['summary']}")
        
        return diagnostics
    
    def _generate_summary(self, diagnostics: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a summary of diagnostic results."""
        summary = {
            'overall_status': 'UNKNOWN',
            'network_issues': [],
            'redis_issues': [],
            'recommendations': []
        }
        
        # Check network connectivity
        network_failures = [test for test in diagnostics['network_tests'] if not test['reachable']]
        if network_failures:
            summary['network_issues'] = [f"{test['hostname']}:{test['port']} - {test['error']}" for test in network_failures]
            summary['recommendations'].append("Check network connectivity and firewall rules")
        
        # Check Redis connections
        redis_failures = [test for test in diagnostics['redis_tests'] if not test['success']]
        if redis_failures:
            summary['redis_issues'] = [test['error'] for test in redis_failures]
            summary['recommendations'].append("Check Redis server status and configuration")
        
        # Determine overall status
        if not network_failures and not redis_failures:
            summary['overall_status'] = 'HEALTHY'
        elif network_failures:
            summary['overall_status'] = 'NETWORK_ISSUES'
        elif redis_failures:
            summary['overall_status'] = 'REDIS_ISSUES'
        else:
            summary['overall_status'] = 'MIXED_ISSUES'
        
        return summary


def debug_celery_redis_connection(celery_app) -> Dict[str, Any]:
    """Debug Redis connection for a Celery app."""
    logger.info("=== DEBUGGING CELERY REDIS CONNECTION ===")
    
    # Get Redis configuration from Celery app
    broker_url = celery_app.conf.get('broker_url')
    result_backend = celery_app.conf.get('result_backend')
    sentinel_enabled = celery_app.conf.get('broker_transport_options', {}).get('master_name') is not None
    
    logger.debug(f"Broker URL: {broker_url}")
    logger.debug(f"Result Backend: {result_backend}")
    logger.debug(f"Sentinel Enabled: {sentinel_enabled}")
    
    # Test broker connection
    broker_debugger = RedisConnectionDebugger(broker_url, sentinel_enabled)
    broker_diagnostics = broker_debugger.run_comprehensive_diagnostics()
    
    # Test result backend connection (if different from broker)
    result_diagnostics = None
    if result_backend != broker_url:
        result_debugger = RedisConnectionDebugger(result_backend, sentinel_enabled)
        result_diagnostics = result_debugger.run_comprehensive_diagnostics()
    
    return {
        'broker_diagnostics': broker_diagnostics,
        'result_backend_diagnostics': result_diagnostics,
        'celery_config': {
            'broker_url': broker_url,
            'result_backend': result_backend,
            'sentinel_enabled': sentinel_enabled,
            'broker_transport_options': celery_app.conf.get('broker_transport_options'),
            'result_backend_transport_options': celery_app.conf.get('result_backend_transport_options'),
        }
    }


def log_redis_connection_info(celery_app):
    """Log detailed Redis connection information for debugging."""
    logger.info("=== REDIS CONNECTION INFORMATION ===")
    
    # Log basic configuration
    logger.info(f"Broker URL: {celery_app.conf.get('broker_url')}")
    logger.info(f"Result Backend: {celery_app.conf.get('result_backend')}")
    logger.info(f"Broker Transport Options: {celery_app.conf.get('broker_transport_options')}")
    logger.info(f"Result Backend Transport Options: {celery_app.conf.get('result_backend_transport_options')}")
    
    # Test connection
    try:
        with celery_app.connection() as conn:
            logger.info(f"Connection established successfully: {conn.as_uri()}")
            logger.info(f"Connection transport: {conn.transport}")
            logger.info(f"Connection hostname: {conn.hostname}")
            logger.info(f"Connection port: {conn.port}")
            
            # Test basic operations
            channel = conn.default_channel
            logger.info(f"Channel created successfully: {channel}")
            
            # Test queue operations
            queues = celery_app.conf.get('task_queues', [])
            for queue in queues:
                if hasattr(queue, 'name'):
                    logger.info(f"Queue: {queue.name}")
                    
    except Exception as e:
        logger.error(f"Failed to establish connection: {e}")
        logger.error(f"Connection error type: {type(e).__name__}")
        
        # Provide specific error guidance
        if "Connection refused" in str(e):
            logger.error("Connection refused - check if Redis server is running")
        elif "timeout" in str(e).lower():
            logger.error("Connection timeout - check network connectivity and Redis server status")
        elif "authentication" in str(e).lower():
            logger.error("Authentication failed - check Redis password configuration")
        elif "sentinel" in str(e).lower():
            logger.error("Sentinel connection failed - check sentinel configuration and master name")
    
    logger.info("=== REDIS CONNECTION INFORMATION END ===") 