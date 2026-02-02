"""
Training service for managing model training jobs
"""
from typing import Dict, Any, Optional, List
import uuid
import subprocess
from datetime import datetime
from models import db, TrainingJob
from exceptions import DatabaseError, NotFoundError
from aws_ec2_helper import trigger_worker_instance
from config import config
import os


class TrainingService:
    """Service for training job operations"""
    
    @staticmethod
    def create_job(data: Dict[str, Any]) -> TrainingJob:
        """
        Create a new training job
        
        Args:
            data: Job parameters
            
        Returns:
            TrainingJob object
        """
        municipio = data.get('municipio', 'blockCV')
        subset = data.get('subset', 'full')
        model_name = data.get('model', 'TabCmpt')
        objective = data.get('objective', 'irm')
        n_step = data.get('n_step', 2)
        
        # Generate unique job ID
        job_id = f"train_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # Create job record
        job = TrainingJob(
            id=job_id,
            job_type='retrain',
            status='pending',
            municipio=municipio,
            subset=subset,
            model_name=model_name,
            objective=objective,
            n_step=n_step,
            progress=0.0,
            progress_message="Job created..."
        )
        
        try:
            db.session.add(job)
            db.session.commit()
            
            # Determine environment: local vs production
            env = os.getenv('FLASK_ENV', os.getenv('ENVIRONMENT', 'local')).lower()
            is_production = env in ['production', 'prod']
            
            if is_production:
                # Production: Launch EC2 worker instance
                job.progress_message = "Job created, waiting for EC2 worker..."
                db.session.commit()
                ec2_instance_id = TrainingService._launch_worker_instance()
                if ec2_instance_id:
                    job.ec2_instance_id = ec2_instance_id
                    job.progress_message = f"EC2 worker instance {ec2_instance_id} launched"
                    db.session.commit()
                else:
                    job.progress_message = "Error launching EC2 worker"
                    job.status = 'failed'
                    db.session.commit()
            else:
                # Local: Spawn local worker subprocess
                job.progress_message = "Job created, starting local worker..."
                db.session.commit()
                TrainingService._start_local_worker(job_id)
                job.progress_message = "Local worker started"
                db.session.commit()
            
            return job
        except Exception as e:
            db.session.rollback()
            raise DatabaseError(f"Failed to create training job: {str(e)}")
    
    @staticmethod
    def _launch_worker_instance() -> Optional[str]:
        """Launch EC2 worker instance (production only)"""
        try:
            launch_template_name = config.EC2_LAUNCH_TEMPLATE_NAME
            instance_info = trigger_worker_instance(launch_template_name=launch_template_name)
            
            if instance_info and isinstance(instance_info, dict):
                return instance_info.get('instance_id')
            return None
        except Exception as e:
            print(f"  ⚠️  Error launching EC2 worker: {str(e)}")
            return None
    
    @staticmethod
    def _start_local_worker(job_id: str):
        """Start local worker subprocess to process training job"""
        try:
            # Get path to worker script
            # __file__ is in services/, so go up one level to reland-backend/
            services_dir = os.path.dirname(os.path.abspath(__file__))
            backend_dir = os.path.dirname(services_dir)  # Go up from services/ to reland-backend/
            worker_script = os.path.join(backend_dir, 'ec2_worker_main.py')
            
            if not os.path.exists(worker_script):
                raise FileNotFoundError(f"Worker script not found: {worker_script}")
            
            # Log worker output so predict-per-DB and other errors are visible
            worker_log_dir = os.path.join(backend_dir, 'worker_logs')
            os.makedirs(worker_log_dir, exist_ok=True)
            worker_log_path = os.path.join(worker_log_dir, f'{job_id}.log')
            worker_log_file = open(worker_log_path, 'w')
            from datetime import datetime, timezone
            worker_log_file.write(f"Worker started for job {job_id} at {datetime.now(timezone.utc).isoformat()}\n")
            worker_log_file.flush()
            import sys
            subprocess.Popen(
                [sys.executable, worker_script, '--job-id', job_id],
                cwd=os.path.dirname(backend_dir),  # Project root
                env=os.environ.copy(),  # Inherit environment (including LOCAL_DATABASE_URL)
                stdout=worker_log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True  # Detach from parent
            )
            print(f"  ✓ Local worker started for job {job_id} (log: {worker_log_path})")
        except Exception as e:
            print(f"  ⚠️  Error starting local worker: {str(e)}")
            raise
    
    @staticmethod
    def get_job(job_id: str) -> TrainingJob:
        """Get job by ID"""
        job = TrainingJob.query.get(job_id)
        if not job:
            raise NotFoundError(f"Job with id {job_id} not found")
        return job
    
    @staticmethod
    def list_jobs(limit: int = 50) -> List[TrainingJob]:
        """List recent training jobs"""
        try:
            return TrainingJob.query.order_by(TrainingJob.created_at.desc()).limit(limit).all()
        except Exception as e:
            raise DatabaseError(f"Failed to list jobs: {str(e)}")

    @staticmethod
    def get_last_trained_model() -> Optional[Dict[str, Any]]:
        """
        Get the most recent successfully completed retrain job (when and what model was trained).

        Returns:
            Dict with last_trained_at, model_name, municipio, experiment_dir, job_id,
            or None if no completed retrain exists.
        """
        try:
            job = (
                TrainingJob.query.filter_by(job_type='retrain', status='completed')
                .order_by(TrainingJob.completed_at.desc())
                .first()
            )
            if not job:
                return None
            result_data = None
            if job.result:
                try:
                    import json
                    result_data = json.loads(job.result)
                except (TypeError, ValueError):
                    result_data = None
            experiment_dir = (result_data.get('experiment_dir') if isinstance(result_data, dict) else None) or ''
            return {
                'last_trained_at': job.completed_at.isoformat() if job.completed_at else None,
                'model_name': job.model_name or 'TabCmpt',
                'municipio': job.municipio or 'blockCV',
                'experiment_dir': experiment_dir,
                'job_id': job.id,
            }
        except Exception as e:
            raise DatabaseError(f"Failed to get last trained model: {str(e)}")
