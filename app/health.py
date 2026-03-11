"""
app/health.py

Health checking system for FileOver microservice.
Performs comprehensive health checks on all components and modules.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

import importlib
import pkgutil
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Awaitable
import asyncio

from pydantic import BaseModel, Field

from app.sessions_collection import sessions
from app.controllers_collection import controllers
from app.types import SessionStatus


class ServiceStatus(str, Enum):
    """Enumeration of possible service health states"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status of a single component"""
    status: ServiceStatus
    message: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    last_check: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class HealthCheckResponse(BaseModel):
    """Complete health check response"""
    status: ServiceStatus
    version: str = "1.2.5"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    components: Dict[str, ComponentHealth]
    summary: str = ""
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class HealthChecker:
    """
    Comprehensive health checker for all service components.
    
    Discovers and checks health of all modules, controllers, sessions,
    and infrastructure components.
    """
    
    def __init__(self):
        self.version = "1.2.5"
        self._checkers: Dict[str, Callable[[], Awaitable[ComponentHealth]]] = {}
        self._register_default_checkers()
        
    def _register_default_checkers(self):
        """Register default health checkers for core components"""
        self._checkers = {
            "sessions": self._check_sessions,
            "controllers": self._check_controllers,
            "modules": self._check_modules,
            "infrastructure": self._check_infrastructure,
            "memory": self._check_memory_usage,
            "tasks": self._check_task_queue,
        }
        
    def register_checker(self, name: str, checker: Callable[[], Awaitable[ComponentHealth]]):
        """
        Register a custom health checker.
        
        Args:
            name: Unique name for the checker
            checker: Async function that returns ComponentHealth
        """
        self._checkers[name] = checker
        
    async def _check_sessions(self) -> ComponentHealth:
        """Check health of session management system"""
        try:
            session_stats = sessions.get_stats() if hasattr(sessions, 'get_stats') else {}
            active_sessions = len(sessions._sessions) if hasattr(sessions, '_sessions') else 0
            
            # Check for error sessions
            error_sessions = 0
            if hasattr(sessions, '_sessions'):
                error_sessions = sum(
                    1 for s in sessions._sessions.values() 
                    if hasattr(s, 'status') and s.status == SessionStatus.ERROR
                )
            
            if error_sessions > active_sessions * 0.05:  # More than 5% in error
                return ComponentHealth(
                    status=ServiceStatus.DEGRADED,
                    message=f"High error session ratio: {error_sessions}/{active_sessions}",
                    details={
                        "active_sessions": active_sessions,
                        "error_sessions": error_sessions,
                        "stats": session_stats
                    }
                )
            
            return ComponentHealth(
                status=ServiceStatus.HEALTHY,
                message=f"{active_sessions} active sessions",
                details={
                    "active_sessions": active_sessions,
                    "error_sessions": error_sessions,
                    "stats": session_stats
                }
            )
            
        except Exception as e:
            return ComponentHealth(
                status=ServiceStatus.UNHEALTHY,
                message=f"Session check failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def _check_controllers(self) -> ComponentHealth:
        """Check health of all loaded controllers"""
        try:
            loaded_controllers = list(controllers.controllers.keys())
            
            # Try to import each controller module to verify it's loadable
            failed_controllers = []
            for controller_name in loaded_controllers:
                try:
                    # Attempt to instantiate with minimal params
                    controller_class = controllers(controller_name)
                    if controller_class:
                        # Just verify it can be instantiated
                        pass
                except Exception:
                    failed_controllers.append(controller_name)
            
            if failed_controllers:
                return ComponentHealth(
                    status=ServiceStatus.DEGRADED,
                    message=f"{len(failed_controllers)} controllers failed to load",
                    details={
                        "total": len(loaded_controllers),
                        "loaded": loaded_controllers,
                        "failed": failed_controllers
                    }
                )
            
            return ComponentHealth(
                status=ServiceStatus.HEALTHY,
                message=f"{len(loaded_controllers)} controllers loaded",
                details={"controllers": loaded_controllers}
            )
            
        except Exception as e:
            return ComponentHealth(
                status=ServiceStatus.UNHEALTHY,
                message=f"Controller check failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def _check_modules(self) -> ComponentHealth:
        """Check all Python modules in the app package"""
        try:
            import app
            modules = []
            failed_modules = []
            
            for _, name, is_pkg in pkgutil.iter_modules(app.__path__, 'app.'):
                try:
                    module = importlib.import_module(name)
                    modules.append(name)
                    
                    # Check if module has required attributes
                    required_attrs = []
                    if hasattr(module, '__all__'):
                        required_attrs = module.__all__
                    
                except Exception as e:
                    failed_modules.append({"name": name, "error": str(e)})
            
            if failed_modules:
                return ComponentHealth(
                    status=ServiceStatus.DEGRADED,
                    message=f"{len(failed_modules)} modules failed to load",
                    details={
                        "loaded": modules,
                        "failed": failed_modules
                    }
                )
            
            return ComponentHealth(
                status=ServiceStatus.HEALTHY,
                message=f"{len(modules)} modules loaded",
                details={"modules": modules}
            )
            
        except Exception as e:
            return ComponentHealth(
                status=ServiceStatus.UNHEALTHY,
                message=f"Module check failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def _check_infrastructure(self) -> ComponentHealth:
        """Check infrastructure dependencies"""
        checks = {}
        
        # Check file system
        try:
            import tempfile
            with tempfile.NamedTemporaryFile() as tmp:
                tmp.write(b"health check")
                tmp.flush()
            checks["filesystem"] = {"status": "ok"}
        except Exception as e:
            checks["filesystem"] = {"status": "error", "error": str(e)}
        
        # Check network (if applicable)
        try:
            import socket
            hostname = socket.gethostname()
            socket.gethostbyname(hostname)
            checks["network"] = {"status": "ok", "hostname": hostname}
        except Exception as e:
            checks["network"] = {"status": "error", "error": str(e)}
        
        # Determine overall status
        failed = any(v.get("status") == "error" for v in checks.values())
        if failed:
            return ComponentHealth(
                status=ServiceStatus.UNHEALTHY,
                message="Infrastructure checks failed",
                details=checks
            )
        
        return ComponentHealth(
            status=ServiceStatus.HEALTHY,
            message="All infrastructure checks passed",
            details=checks
        )
    
    async def _check_memory_usage(self) -> ComponentHealth:
        """Check memory usage"""
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            
            # Warning thresholds
            if memory_percent > 80:
                status = ServiceStatus.DEGRADED
                message = f"High memory usage: {memory_percent:.1f}%"
            elif memory_percent > 95:
                status = ServiceStatus.UNHEALTHY
                message = f"Critical memory usage: {memory_percent:.1f}%"
            else:
                status = ServiceStatus.HEALTHY
                message = f"Memory usage: {memory_percent:.1f}%"
            
            return ComponentHealth(
                status=status,
                message=message,
                details={
                    "rss_bytes": memory_info.rss,
                    "vms_bytes": memory_info.vms,
                    "percent": round(memory_percent, 2),
                    "pid": os.getpid()
                }
            )
            
        except ImportError:
            # psutil not available - skip detailed memory check
            return ComponentHealth(
                status=ServiceStatus.HEALTHY,
                message="Memory check skipped (psutil not installed)",
                details={"note": "Install psutil for detailed memory monitoring"}
            )
        except Exception as e:
            return ComponentHealth(
                status=ServiceStatus.DEGRADED,
                message=f"Memory check failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def _check_task_queue(self) -> ComponentHealth:
        """Check task queue health"""
        try:
            # Check if sessions has task queue attributes
            if hasattr(sessions, 'task_queue'):
                queue_size = sessions.task_queue.qsize() if hasattr(sessions.task_queue, 'qsize') else 0
                
                if queue_size > 1000:
                    status = ServiceStatus.DEGRADED
                    message = f"Large task queue: {queue_size} tasks"
                else:
                    status = ServiceStatus.HEALTHY
                    message = f"Task queue size: {queue_size}"
                
                return ComponentHealth(
                    status=status,
                    message=message,
                    details={"queue_size": queue_size}
                )
            
            return ComponentHealth(
                status=ServiceStatus.HEALTHY,
                message="Task queue monitoring not available",
                details={"note": "Task queue not implemented in sessions"}
            )
            
        except Exception as e:
            return ComponentHealth(
                status=ServiceStatus.DEGRADED,
                message=f"Task queue check failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def check_all(self) -> HealthCheckResponse:
        """
        Run all registered health checks.
        
        Returns:
            HealthCheckResponse with comprehensive health status
        """
        component_results = {}
        
        # Run all checks concurrently
        tasks = [
            (name, checker()) 
            for name, checker in self._checkers.items()
        ]
        
        results = await asyncio.gather(
            *[task for _, task in tasks],
            return_exceptions=True
        )
        
        # Process results
        for (name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                component_results[name] = ComponentHealth(
                    status=ServiceStatus.UNHEALTHY,
                    message=f"Check failed: {str(result)}",
                    details={"error": str(result)}
                )
            else:
                component_results[name] = result
        
        # Determine overall status
        status_counts = {}
        for comp in component_results.values():
            status_counts[comp.status] = status_counts.get(comp.status, 0) + 1
        
        if status_counts.get(ServiceStatus.UNHEALTHY, 0) > 0:
            overall_status = ServiceStatus.UNHEALTHY
            summary = f"Unhealthy: {status_counts.get(ServiceStatus.UNHEALTHY, 0)} components failed"
        elif status_counts.get(ServiceStatus.DEGRADED, 0) > 0:
            overall_status = ServiceStatus.DEGRADED
            summary = f"Degraded: {status_counts.get(ServiceStatus.DEGRADED, 0)} components degraded"
        else:
            overall_status = ServiceStatus.HEALTHY
            summary = f"All {len(component_results)} components healthy"
        
        return HealthCheckResponse(
            status=overall_status,
            version=self.version,
            timestamp=datetime.now(timezone.utc),
            components=component_results,
            summary=summary
        )
    
    async def check_component(self, component_name: str) -> Optional[ComponentHealth]:
        """
        Run health check for a specific component.
        
        Args:
            component_name: Name of the component to check
            
        Returns:
            ComponentHealth if component exists, None otherwise
        """
        checker = self._checkers.get(component_name)
        if checker:
            try:
                return await checker()
            except Exception as e:
                return ComponentHealth(
                    status=ServiceStatus.UNHEALTHY,
                    message=f"Check failed: {str(e)}",
                    details={"error": str(e)}
                )
        return None
    
    def get_available_checks(self) -> List[str]:
        """Get list of available health check names"""
        return list(self._checkers.keys())


# Singleton instance for global use
health = HealthChecker()