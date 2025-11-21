"""
Airflow DAG Trigger Service

Handles triggering Airflow DAGs via the REST API for event-driven job processing.
Uses Airflow 3.x API v2 endpoints.
"""
import requests
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)


class AirflowTriggerService:
    """
    Service for triggering Airflow DAGs via REST API.

    Features:
    - Event-driven DAG triggering
    - Airflow 3.x API v2 compatibility
    - JWT token authentication
    - Error handling and logging
    """

    def __init__(self):
        """Initialize Airflow trigger service with configuration."""
        self.airflow_url = getattr(settings, 'AIRFLOW_URL', 'http://airflow-webserver:8080')
        self.airflow_user = getattr(settings, 'AIRFLOW_ADMIN_USER', 'admin')
        self.airflow_password = getattr(settings, 'AIRFLOW_ADMIN_PASSWORD', 'admin')
        self.timeout = 10  # seconds
        self._token = None  # Cached JWT token
        self._token_expires = None

    def _get_jwt_token(self) -> str:
        """
        Get JWT token for Airflow API authentication.

        Per Airflow 3.x documentation, the public API uses JWT authentication.
        Endpoint: POST /auth/token with username/password

        Returns:
            str: JWT access token

        Raises:
            Exception: If token generation fails
        """
        # Check if we have a cached valid token
        if self._token and self._token_expires:
            if datetime.now(timezone.utc) < self._token_expires:
                return self._token

        # Generate new token - Airflow 3.x endpoint
        token_url = f"{self.airflow_url}/auth/token"

        try:
            logger.info(f"Generating JWT token for Airflow API authentication")

            response = requests.post(
                token_url,
                json={
                    "username": self.airflow_user,
                    "password": self.airflow_password
                },
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )

            if response.status_code in (200, 201):
                token_data = response.json()
                self._token = token_data.get("access_token")

                # Cache token (tokens typically valid for 1 hour, we'll refresh after 50 min)
                from datetime import timedelta
                self._token_expires = datetime.now(timezone.utc) + timedelta(minutes=50)

                logger.info("✅ JWT token generated successfully")
                return self._token
            else:
                error_msg = f"Failed to get JWT token: HTTP {response.status_code} - {response.text}"
                logger.error(f"❌ {error_msg}")
                raise Exception(error_msg)

        except requests.exceptions.RequestException as e:
            error_msg = f"Error getting JWT token: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)

    def trigger_video_transcoding_dag(
        self,
        job_id: str,
        source_path: str,
        priority: int = 5,
        extra_conf: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Trigger the video transcoding DAG for a specific job.

        Uses JWT Bearer token authentication as required by Airflow 3.x Public API.

        Args:
            job_id: Unique job identifier
            source_path: Path to the source video file
            priority: int = 5
            extra_conf: Additional configuration parameters

        Returns:
            dict: DAG run information including dag_run_id and state

        Raises:
            Exception: If DAG trigger fails
        """
        dag_id = "video_transcoding_pipeline"

        # Build DAG configuration
        dag_conf = {
            "job_id": job_id,
            "source_path": source_path,
            "priority": priority,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        }

        # Merge extra configuration
        if extra_conf:
            dag_conf.update(extra_conf)

        # Build request payload (Airflow 3.x API v2 format)
        payload = {
            "logical_date": datetime.now(timezone.utc).isoformat(),
            "conf": dag_conf,
            "note": f"Triggered by API for job {job_id}"
        }

        # Get JWT token for authentication
        token = self._get_jwt_token()

        # Trigger DAG via Airflow REST API using JWT Bearer token
        url = f"{self.airflow_url}/api/v2/dags/{dag_id}/dagRuns"

        try:
            logger.info(f"Triggering Airflow DAG '{dag_id}' for job {job_id}")

            response = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                timeout=self.timeout
            )

            # Check response
            if response.status_code == 200:
                dag_run_info = response.json()
                dag_run_id = dag_run_info.get("dag_run_id")
                state = dag_run_info.get("state")

                logger.info(
                    f"✅ DAG '{dag_id}' triggered successfully for job {job_id} "
                    f"(dag_run_id: {dag_run_id}, state: {state})"
                )

                return dag_run_info

            else:
                error_msg = f"Failed to trigger DAG: HTTP {response.status_code} - {response.text}"
                logger.error(f"❌ {error_msg}")
                raise Exception(error_msg)

        except requests.exceptions.Timeout:
            error_msg = f"Timeout while triggering DAG '{dag_id}' for job {job_id}"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)

        except requests.exceptions.RequestException as e:
            error_msg = f"Error triggering DAG '{dag_id}' for job {job_id}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)

    def get_dag_run_status(self, dag_id: str, dag_run_id: str) -> Dict[str, Any]:
        """
        Get the status of a specific DAG run.

        Uses JWT Bearer token authentication.

        Args:
            dag_id: DAG identifier
            dag_run_id: DAG run identifier

        Returns:
            dict: DAG run status information
        """
        url = f"{self.airflow_url}/api/v2/dags/{dag_id}/dagRuns/{dag_run_id}"

        try:
            token = self._get_jwt_token()

            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Failed to get DAG run status: HTTP {response.status_code}")
                return {}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting DAG run status: {str(e)}")
            return {}


# Global instance
airflow_trigger_service = AirflowTriggerService()
