"""
Airflow DAG for Storage Cleanup Pipeline

Sprint 4: Storage & File Management

Automated cleanup DAG that runs daily to:
- Clean up temporary files older than 1 day
- Remove failed job outputs older than 7 days
- Delete old thumbnails after 30 days
- Find and remove orphaned files
- Generate cleanup reports
"""
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys
import logging

# Add app to Python path for imports
sys.path.insert(0, '/code/app')

from storage.cleanup import StorageCleanupService, CleanupRule
from storage.deduplication import DuplicateDetector
from core.config import Settings
from minio import Minio

logger = logging.getLogger(__name__)


# ============================================================================
# DAG CONFIGURATION
# ============================================================================

default_args = {
    'owner': 'transcode-flow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_minio_client():
    """Create MinIO client instance"""
    settings = Settings()

    return Minio(
        endpoint=settings.MINIO_ENDPOINT.replace('http://', '').replace('https://', ''),
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE
    )


# ============================================================================
# TASK FUNCTIONS
# ============================================================================

def cleanup_temp_files_task(**context):
    """
    Task 1: Clean up temporary files older than 1 day
    """
    logger.info("Starting cleanup of temporary files...")

    client = get_minio_client()
    settings = Settings()

    cleanup_service = StorageCleanupService(
        client,
        settings.MINIO_BUCKET_NAME,
        custom_rules=[
            CleanupRule(
                name="cleanup-temp-files",
                prefix="temp/",
                max_age_days=1,
                description="Remove temporary files older than 1 day"
            )
        ]
    )

    # Run cleanup (not dry-run)
    results = cleanup_service.cleanup_all(dry_run=False)

    # Log results
    for result in results:
        logger.info(
            f"Cleanup {result.rule_name}: "
            f"{result.files_deleted} files deleted, "
            f"{result.space_freed_mb:.2f}MB freed"
        )

    # Push results to XCom
    context['task_instance'].xcom_push(
        key='temp_cleanup_result',
        value={
            'files_deleted': sum(r.files_deleted for r in results),
            'space_freed_mb': sum(r.space_freed_mb for r in results)
        }
    )

    logger.info("Temporary files cleanup completed")


def cleanup_failed_jobs_task(**context):
    """
    Task 2: Clean up failed job outputs older than 7 days
    """
    logger.info("Starting cleanup of failed job outputs...")

    client = get_minio_client()
    settings = Settings()

    cleanup_service = StorageCleanupService(
        client,
        settings.MINIO_BUCKET_NAME,
        custom_rules=[
            CleanupRule(
                name="cleanup-failed-jobs",
                prefix="failed/",
                max_age_days=7,
                description="Remove failed job files older than 7 days"
            )
        ]
    )

    # Run cleanup (not dry-run)
    results = cleanup_service.cleanup_all(dry_run=False)

    # Log results
    for result in results:
        logger.info(
            f"Cleanup {result.rule_name}: "
            f"{result.files_deleted} files deleted, "
            f"{result.space_freed_mb:.2f}MB freed"
        )

    # Push results to XCom
    context['task_instance'].xcom_push(
        key='failed_cleanup_result',
        value={
            'files_deleted': sum(r.files_deleted for r in results),
            'space_freed_mb': sum(r.space_freed_mb for r in results)
        }
    )

    logger.info("Failed job cleanup completed")


def cleanup_old_thumbnails_task(**context):
    """
    Task 3: Clean up thumbnails older than 30 days
    """
    logger.info("Starting cleanup of old thumbnails...")

    client = get_minio_client()
    settings = Settings()

    cleanup_service = StorageCleanupService(
        client,
        settings.MINIO_BUCKET_NAME,
        custom_rules=[
            CleanupRule(
                name="cleanup-old-thumbnails",
                prefix="thumbnails/",
                max_age_days=30,
                description="Remove thumbnails older than 30 days"
            )
        ]
    )

    # Run cleanup (not dry-run)
    results = cleanup_service.cleanup_all(dry_run=False)

    # Log results
    for result in results:
        logger.info(
            f"Cleanup {result.rule_name}: "
            f"{result.files_deleted} files deleted, "
            f"{result.space_freed_mb:.2f}MB freed"
        )

    # Push results to XCom
    context['task_instance'].xcom_push(
        key='thumbnail_cleanup_result',
        value={
            'files_deleted': sum(r.files_deleted for r in results),
            'space_freed_mb': sum(r.space_freed_mb for r in results)
        }
    )

    logger.info("Thumbnail cleanup completed")


def scan_for_duplicates_task(**context):
    """
    Task 4: Scan for duplicate files
    """
    logger.info("Starting duplicate file scan...")

    client = get_minio_client()
    settings = Settings()

    detector = DuplicateDetector(client, settings.MINIO_BUCKET_NAME)

    # Scan entire bucket
    scan_results = detector.scan_bucket(recursive=True)

    logger.info(
        f"Duplicate scan completed: "
        f"{scan_results['total_duplicates']} duplicates found, "
        f"{scan_results['wasted_space_gb']:.4f}GB wasted"
    )

    # Push results to XCom
    context['task_instance'].xcom_push(
        key='duplicate_scan_result',
        value={
            'total_duplicates': scan_results['total_duplicates'],
            'wasted_space_gb': scan_results['wasted_space_gb'],
            'duplicate_groups': scan_results['duplicate_groups']
        }
    )

    logger.info("Duplicate scan completed")


def generate_cleanup_report_task(**context):
    """
    Task 5: Generate and log cleanup report
    """
    logger.info("Generating cleanup report...")

    ti = context['task_instance']

    # Pull results from previous tasks
    temp_result = ti.xcom_pull(key='temp_cleanup_result', task_ids='cleanup_temp_files')
    failed_result = ti.xcom_pull(key='failed_cleanup_result', task_ids='cleanup_failed_jobs')
    thumbnail_result = ti.xcom_pull(key='thumbnail_cleanup_result', task_ids='cleanup_old_thumbnails')
    duplicate_result = ti.xcom_pull(key='duplicate_scan_result', task_ids='scan_for_duplicates')

    # Calculate totals
    total_files_deleted = (
        temp_result.get('files_deleted', 0) +
        failed_result.get('files_deleted', 0) +
        thumbnail_result.get('files_deleted', 0)
    )

    total_space_freed_mb = (
        temp_result.get('space_freed_mb', 0) +
        failed_result.get('space_freed_mb', 0) +
        thumbnail_result.get('space_freed_mb', 0)
    )

    # Generate report
    report = []
    report.append("=" * 60)
    report.append("STORAGE CLEANUP REPORT")
    report.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 60)
    report.append("")
    report.append("CLEANUP SUMMARY:")
    report.append(f"  Total files deleted: {total_files_deleted}")
    report.append(f"  Total space freed: {total_space_freed_mb:.2f} MB ({total_space_freed_mb / 1024:.4f} GB)")
    report.append("")
    report.append("BREAKDOWN:")
    report.append(f"  Temp files: {temp_result.get('files_deleted', 0)} files, {temp_result.get('space_freed_mb', 0):.2f} MB")
    report.append(f"  Failed jobs: {failed_result.get('files_deleted', 0)} files, {failed_result.get('space_freed_mb', 0):.2f} MB")
    report.append(f"  Thumbnails: {thumbnail_result.get('files_deleted', 0)} files, {thumbnail_result.get('space_freed_mb', 0):.2f} MB")
    report.append("")
    report.append("DUPLICATE FILES:")
    report.append(f"  Duplicate groups: {duplicate_result.get('duplicate_groups', 0)}")
    report.append(f"  Total duplicates: {duplicate_result.get('total_duplicates', 0)}")
    report.append(f"  Wasted space: {duplicate_result.get('wasted_space_gb', 0):.4f} GB")
    report.append("=" * 60)

    report_text = "\n".join(report)
    logger.info(f"\n{report_text}")

    # Push report to XCom
    context['task_instance'].xcom_push(
        key='cleanup_report',
        value=report_text
    )

    logger.info("Cleanup report generated")


with DAG(
    'storage_cleanup_pipeline',
    default_args=default_args,
    description='Automated storage cleanup and maintenance',
    schedule='0 2 * * *',  # Run daily at 2 AM (changed from schedule_interval in Airflow 3)
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['storage', 'cleanup', 'maintenance'],
    max_active_runs=1,
) as dag:

    # ============================================================================
    # TASK DEFINITIONS
    # ============================================================================

    # Task 1: Cleanup temporary files
    cleanup_temp_files = PythonOperator(
        task_id='cleanup_temp_files',
        python_callable=cleanup_temp_files_task,
    )

    # Task 2: Cleanup failed jobs
    cleanup_failed_jobs = PythonOperator(
        task_id='cleanup_failed_jobs',
        python_callable=cleanup_failed_jobs_task,
    )

    # Task 3: Cleanup old thumbnails
    cleanup_old_thumbnails = PythonOperator(
        task_id='cleanup_old_thumbnails',
        python_callable=cleanup_old_thumbnails_task,
    )

    # Task 4: Scan for duplicates
    scan_for_duplicates = PythonOperator(
        task_id='scan_for_duplicates',
        python_callable=scan_for_duplicates_task,
    )

    # Task 5: Generate cleanup report
    generate_cleanup_report = PythonOperator(
        task_id='generate_cleanup_report',
        python_callable=generate_cleanup_report_task,
    )


    # ============================================================================
    # TASK DEPENDENCIES
    # ============================================================================

    # Run cleanup tasks in parallel
    [cleanup_temp_files, cleanup_failed_jobs, cleanup_old_thumbnails] >> scan_for_duplicates

    # Generate report after all tasks complete
    scan_for_duplicates >> generate_cleanup_report
