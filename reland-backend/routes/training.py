"""
Training job routes
"""
from flask import jsonify, request
from routes import api_bp
from services.training_service import TrainingService
from exceptions import RELandException


@api_bp.route('/retrain_model', methods=['POST'])
def retrain_model():
    """Retrain the model with updated labels and confirmed events"""
    try:
        data = request.json or {}
        job = TrainingService.create_job(data)
        
        response = {
            "message": "Model training job created successfully",
            "job_id": job.id,
            "status": job.status,
            "ec2_instance_id": job.ec2_instance_id,
            "status_url": f"/api/job_status/{job.id}"
        }
        
        status_code = 202 if job.status == 'pending' else 500
        return jsonify(response), status_code
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route('/job_status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get the status of a training job"""
    try:
        job = TrainingService.get_job(job_id)
        
        response = {
            "job_id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "progress": job.progress,
            "progress_message": job.progress_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "ec2_instance_id": job.ec2_instance_id
        }
        
        # Add result if job is completed
        if job.status == 'completed' and job.result:
            try:
                import json
                response['result'] = json.loads(job.result)
            except (json.JSONDecodeError, TypeError):
                response['result'] = job.result
        
        # Add error if job failed
        if job.status == 'failed':
            response['error'] = job.error_message or "Job failed"
        
        return jsonify(response), 200
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({
            "error": "Failed to get job status",
            "message": str(e)
        }), 500


@api_bp.route('/jobs/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    """Cancel a pending or running training job (marks as failed with 'Cancelled by user')."""
    try:
        job = TrainingService.cancel_job(job_id)
        return jsonify({
            "message": "Job cancelled",
            "job_id": job.id,
            "status": job.status,
        }), 200
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({
            "error": "Failed to cancel job",
            "message": str(e)
        }), 500


@api_bp.route('/jobs', methods=['GET'])
def list_jobs():
    """List recent training jobs"""
    try:
        limit = request.args.get('limit', 50, type=int)
        jobs = TrainingService.list_jobs(limit)
        return jsonify({
            "jobs": [job.to_dict() for job in jobs]
        }), 200
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({
            "error": "Failed to list jobs",
            "message": str(e)
        }), 500


@api_bp.route('/last_trained_model', methods=['GET'])
def get_last_trained_model():
    """Get when the last model was trained and its name (from most recent completed retrain job)."""
    try:
        info = TrainingService.get_last_trained_model()
        if not info:
            return jsonify({
                "message": "No model has been trained yet",
                "last_trained_at": None,
                "model_name": None,
                "municipio": None,
                "experiment_dir": None,
                "job_id": None
            }), 200
        return jsonify(info), 200
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({
            "error": "Failed to get last trained model",
            "message": str(e)
        }), 500
