"""
DataGenie AI - LLM Router

Smart routing between local (Ollama) and cloud (Claude) LLMs
based on query complexity, resource availability, and cost.
"""

import logging
from typing import Dict, Any, Optional, List
from enum import Enum

from .ollama_service import OllamaService
from .claude_service import ClaudeService
from ..config import settings

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Task types for routing decisions."""
    SIMPLE_SQL = "simple_sql"
    COMPLEX_SQL = "complex_sql"
    INTENT_CLASSIFICATION = "intent_classification"
    ENTITY_EXTRACTION = "entity_extraction"
    RAG_SYNTHESIS = "rag_synthesis"
    EXECUTIVE_SUMMARY = "executive_summary"
    EXPLANATION = "explanation"
    VALIDATION = "validation"


class LLMRouter:
    """
    Intelligent LLM router for hybrid local/cloud deployment.
    
    Routing Strategy:
    - Simple tasks → Local Ollama (fast, free)
    - Complex tasks → Claude API (accurate, paid)
    - Fallback logic when primary unavailable
    """

    # Routing configuration
    LOCAL_TASKS = {
        TaskType.SIMPLE_SQL,
        TaskType.INTENT_CLASSIFICATION,
        TaskType.ENTITY_EXTRACTION,
        TaskType.VALIDATION,
    }

    CLOUD_TASKS = {
        TaskType.COMPLEX_SQL,
        TaskType.RAG_SYNTHESIS,
        TaskType.EXECUTIVE_SUMMARY,
        TaskType.EXPLANATION,
    }

    def __init__(self):
        """Initialize LLM router with available services."""
        self._ollama: Optional[OllamaService] = None
        self._claude: Optional[ClaudeService] = None
        self._initialize_services()

    def _initialize_services(self):
        """Initialize available LLM services."""
        # Initialize Ollama if enabled
        if settings.use_local_llm:
            try:
                self._ollama = OllamaService()
                if self._ollama.is_available():
                    logger.info("Ollama service initialized")
                else:
                    logger.warning("Ollama not available, will use cloud fallback")
            except Exception as e:
                logger.warning(f"Failed to initialize Ollama: {e}")

        # Initialize Claude if API key available
        if settings.has_anthropic_key:
            try:
                self._claude = ClaudeService()
                logger.info("Claude service initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Claude: {e}")

        # Verify at least one service is available
        if not self._is_any_available():
            logger.error("No LLM services available!")

    def _is_any_available(self) -> bool:
        """Check if any LLM service is available."""
        ollama_ok = self._ollama and self._ollama.is_available()
        claude_ok = self._claude is not None
        return ollama_ok or claude_ok

    def get_status(self) -> Dict[str, Any]:
        """
        Get status of all LLM services.
        
        Returns:
            Dict with service availability status
        """
        return {
            "ollama": {
                "enabled": settings.use_local_llm,
                "available": self._ollama.is_available() if self._ollama else False,
                "model": settings.ollama_model,
            },
            "claude": {
                "enabled": settings.has_anthropic_key,
                "available": self._claude is not None,
                "model": settings.anthropic_model,
            }
        }

    def route_query(
        self,
        prompt: str,
        task_type: TaskType | str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        force_provider: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Route query to appropriate LLM based on task type.
        
        Args:
            prompt: User prompt
            task_type: Type of task (determines routing)
            system_prompt: Optional system instructions
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            force_provider: Override routing ('ollama' or 'claude')
            **kwargs: Additional parameters
            
        Returns:
            Dict with 'content', 'provider', 'tokens', 'cost'
        """
        # Convert string to enum if needed
        if isinstance(task_type, str):
            try:
                task_type = TaskType(task_type)
            except ValueError:
                task_type = TaskType.SIMPLE_SQL

        logger.info(f"Routing task: {task_type.value}")

        # Handle forced provider
        if force_provider:
            return self._route_to_provider(
                force_provider, prompt, system_prompt, max_tokens, temperature, **kwargs
            )

        # Smart routing based on task type
        if task_type in self.LOCAL_TASKS:
            # Try local first, fallback to cloud
            return self._route_local_first(
                prompt, system_prompt, max_tokens, temperature, task_type, **kwargs
            )
        else:
            # Try cloud first, fallback to local
            return self._route_cloud_first(
                prompt, system_prompt, max_tokens, temperature, task_type, **kwargs
            )

    def _route_local_first(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float,
        task_type: TaskType,
        **kwargs
    ) -> Dict[str, Any]:
        """Route to local LLM first with cloud fallback."""
        # Try Ollama first
        if self._ollama and self._ollama.is_available():
            try:
                logger.info(f"Routing {task_type.value} to Ollama (local)")
                result = self._ollama.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs
                )
                result["cost"] = 0.0  # Local is free
                return result
            except Exception as e:
                logger.warning(f"Ollama failed, trying Claude: {e}")

        # Fallback to Claude
        if self._claude:
            logger.info(f"Falling back to Claude for {task_type.value}")
            return self._claude.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )

        raise RuntimeError("No LLM available for task")

    def _route_cloud_first(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float,
        task_type: TaskType,
        **kwargs
    ) -> Dict[str, Any]:
        """Route to cloud LLM first with local fallback."""
        # Try Claude first for complex tasks
        if self._claude:
            try:
                logger.info(f"Routing {task_type.value} to Claude (cloud)")
                return self._claude.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs
                )
            except Exception as e:
                logger.warning(f"Claude failed, trying Ollama: {e}")

        # Fallback to Ollama
        if self._ollama and self._ollama.is_available():
            logger.info(f"Falling back to Ollama for {task_type.value}")
            result = self._ollama.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            result["cost"] = 0.0
            return result

        raise RuntimeError("No LLM available for task")

    def _route_to_provider(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Force routing to specific provider."""
        if provider.lower() == "ollama":
            if not self._ollama or not self._ollama.is_available():
                raise RuntimeError("Ollama not available")
            result = self._ollama.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            result["cost"] = 0.0
            return result

        elif provider.lower() == "claude":
            if not self._claude:
                raise RuntimeError("Claude not configured")
            return self._claude.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )

        raise ValueError(f"Unknown provider: {provider}")

    def estimate_cost(
        self,
        task_type: TaskType | str,
        estimated_tokens: int = 1000
    ) -> Dict[str, float]:
        """
        Estimate cost for different routing decisions.
        
        Args:
            task_type: Type of task
            estimated_tokens: Estimated token count
            
        Returns:
            Dict with cost estimates per provider
        """
        # Convert string to enum
        if isinstance(task_type, str):
            try:
                task_type = TaskType(task_type)
            except ValueError:
                task_type = TaskType.SIMPLE_SQL

        # Ollama is always free
        ollama_cost = 0.0

        # Claude cost (Sonnet pricing)
        # Assume ~40% input, 60% output split
        input_tokens = int(estimated_tokens * 0.4)
        output_tokens = int(estimated_tokens * 0.6)
        claude_cost = (input_tokens * 3.0 / 1_000_000) + (output_tokens * 15.0 / 1_000_000)

        return {
            "ollama": ollama_cost,
            "claude": round(claude_cost, 6),
            "recommended": "ollama" if task_type in self.LOCAL_TASKS else "claude",
            "task_type": task_type.value
        }

    def analyze_query_complexity(self, query: str) -> Dict[str, Any]:
        """
        Analyze query complexity to determine best routing.
        
        Args:
            query: Natural language query
            
        Returns:
            Dict with complexity analysis
        """
        query_lower = query.lower()

        # Complex indicators
        complex_indicators = [
            "join", "subquery", "having", "window function", "partition",
            "case when", "union", "intersect", "complex", "nested",
            "multiple tables", "across", "compare", "trend", "forecast"
        ]

        # Medium indicators
        medium_indicators = [
            "group by", "order by", "filter", "aggregate", "sum", "count",
            "average", "total", "by region", "by month", "top", "bottom"
        ]

        # Count indicators
        complex_count = sum(1 for ind in complex_indicators if ind in query_lower)
        medium_count = sum(1 for ind in medium_indicators if ind in query_lower)

        # Determine complexity
        if complex_count >= 2 or (complex_count >= 1 and medium_count >= 2):
            complexity = "high"
            recommended_task = TaskType.COMPLEX_SQL
        elif medium_count >= 2 or complex_count >= 1:
            complexity = "medium"
            recommended_task = TaskType.COMPLEX_SQL
        else:
            complexity = "low"
            recommended_task = TaskType.SIMPLE_SQL

        return {
            "complexity": complexity,
            "recommended_task_type": recommended_task.value,
            "complex_indicators_found": complex_count,
            "medium_indicators_found": medium_count,
            "recommended_provider": "ollama" if complexity == "low" else "claude"
        }


# Create singleton instance
_router_instance: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Get or create LLM router singleton."""
    global _router_instance
    if _router_instance is None:
        _router_instance = LLMRouter()
    return _router_instance
