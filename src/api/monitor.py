"""
Performance Monitoring Dashboard
Tracks async queue, cache, and connection pool performance
"""
from flask import Blueprint, jsonify, render_template_string
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

monitor_bp = Blueprint('monitor', __name__)

@monitor_bp.route('/api/performance-stats')
def get_performance_stats():
    """Get comprehensive performance statistics."""
    try:
        stats = {
            'timestamp': datetime.now().isoformat(),
            'queue': {},
            'cache': {},
            'connection_pool': {},
            'system': {}
        }
        
        # Queue stats
        try:
            from src.utils.async_queue import _verification_queue
            if _verification_queue:
                stats['queue'] = _verification_queue.get_queue_stats()
        except Exception as e:
            stats['queue'] = {'error': str(e)}
        
        # Cache stats
        try:
            from src.utils.memory_cache import get_session_cache
            session_cache = get_session_cache()
            if session_cache:
                stats['cache'] = session_cache.get_cache_stats()
        except Exception as e:
            stats['cache'] = {'error': str(e)}
        
        # Connection pool stats
        try:
            from src.utils.connection_pool import _connection_pool
            if _connection_pool:
                stats['connection_pool'] = _connection_pool.get_stats()
        except Exception as e:
            stats['connection_pool'] = {'error': str(e)}
        
        # System stats
        try:
            import psutil
            stats['system'] = {
                'cpu_percent': psutil.cpu_percent(),
                'memory_percent': psutil.virtual_memory().percent,
                'active_threads': threading.active_count()
            }
        except ImportError:
            import os, threading
            stats['system'] = {
                'cpu_count': os.cpu_count(),
                'active_threads': threading.active_count()
            }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Performance stats error: {e}")
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/performance-dashboard')
def performance_dashboard():
    """Performance monitoring dashboard."""
    
    dashboard_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Face Recognition Performance Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; }
            .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }
            .stat-item { background: #f8f9fa; padding: 15px; border-radius: 6px; border-left: 4px solid #007bff; }
            .stat-value { font-size: 24px; font-weight: bold; color: #007bff; }
            .stat-label { color: #666; font-size: 14px; }
            .status-good { border-left-color: #28a745; }
            .status-warning { border-left-color: #ffc107; }
            .status-error { border-left-color: #dc3545; }
            .refresh-btn { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
            .timestamp { color: #666; font-size: 12px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Face Recognition Performance Dashboard</h1>
            
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h2>System Performance</h2>
                    <button class="refresh-btn" onclick="refreshStats()">🔄 Refresh</button>
                </div>
                <div class="timestamp" id="lastUpdate">Loading...</div>
            </div>
            
            <div class="card">
                <h3>📋 Async Verification Queue</h3>
                <div class="stats-grid" id="queueStats">
                    <div class="stat-item">
                        <div class="stat-value" id="queueSize">-</div>
                        <div class="stat-label">Queue Size</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="activeTasks">-</div>
                        <div class="stat-label">Active Tasks</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="workerCount">-</div>
                        <div class="stat-label">Workers</div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>💾 Session Cache</h3>
                <div class="stats-grid" id="cacheStats">
                    <div class="stat-item">
                        <div class="stat-value" id="activeSessions">-</div>
                        <div class="stat-label">Active Sessions</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="cacheSize">-</div>
                        <div class="stat-label">Cache Size (MB)</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="totalSessions">-</div>
                        <div class="stat-label">Total Sessions</div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>🔗 Connection Pool</h3>
                <div class="stats-grid" id="poolStats">
                    <div class="stat-item">
                        <div class="stat-value" id="poolSize">-</div>
                        <div class="stat-label">Available Connections</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="activeConnections">-</div>
                        <div class="stat-label">Active Connections</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="utilization">-</div>
                        <div class="stat-label">Utilization %</div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>🖥️ System Resources</h3>
                <div class="stats-grid" id="systemStats">
                    <div class="stat-item">
                        <div class="stat-value" id="cpuUsage">-</div>
                        <div class="stat-label">CPU Usage %</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="memoryUsage">-</div>
                        <div class="stat-label">Memory Usage %</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="activeThreads">-</div>
                        <div class="stat-label">Active Threads</div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            function refreshStats() {
                fetch('/api/performance-stats')
                    .then(response => response.json())
                    .then(data => {
                        updateDashboard(data);
                    })
                    .catch(error => {
                        console.error('Error fetching stats:', error);
                    });
            }
            
            function updateDashboard(data) {
                // Update timestamp
                document.getElementById('lastUpdate').textContent = 'Last updated: ' + new Date(data.timestamp).toLocaleString();
                
                // Update queue stats
                if (data.queue && !data.queue.error) {
                    document.getElementById('queueSize').textContent = data.queue.queue_size || 0;
                    document.getElementById('activeTasks').textContent = data.queue.active_tasks || 0;
                    document.getElementById('workerCount').textContent = data.queue.worker_count || 0;
                }
                
                // Update cache stats
                if (data.cache && !data.cache.error) {
                    document.getElementById('activeSessions').textContent = data.cache.active_sessions || 0;
                    document.getElementById('cacheSize').textContent = data.cache.cache_size_mb || 0;
                    document.getElementById('totalSessions').textContent = data.cache.total_sessions || 0;
                }
                
                // Update connection pool stats
                if (data.connection_pool && !data.connection_pool.error) {
                    document.getElementById('poolSize').textContent = data.connection_pool.pool_size || 0;
                    document.getElementById('activeConnections').textContent = data.connection_pool.active_connections || 0;
                    document.getElementById('utilization').textContent = data.connection_pool.utilization || 0;
                }
                
                // Update system stats
                if (data.system && !data.system.error) {
                    document.getElementById('cpuUsage').textContent = data.system.cpu_percent || '-';
                    document.getElementById('memoryUsage').textContent = data.system.memory_percent || '-';
                    document.getElementById('activeThreads').textContent = data.system.active_threads || 0;
                }
            }
            
            // Auto-refresh every 5 seconds
            setInterval(refreshStats, 5000);
            
            // Initial load
            refreshStats();
        </script>
    </body>
    </html>
    """
    
    return dashboard_html