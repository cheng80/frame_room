"""Empty animation results must not be published as successful library work."""
import pytest

from services.api import store as s
from services.worker.main import publish


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'DATA', tmp_path / 'data')
    s.init()
    return s.create_project('게시 guard 시험', '')


def make_job(project, operation):
    jid, attempt = s.uid(), s.uid()
    job = dict(jobId=jid, projectId=project['projectId'], operation=operation, status='running',
               attemptId=attempt, inputRevision=project['revision'], snapshot=project,
               requestHash='test', idempotencyKey=jid, eventSeq=0, artifacts=[], errors=[],
               createdAt=s.now(), updatedAt=s.now())
    with s.connect() as db:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)',
                   (jid, job['projectId'], operation, job['status'], 'test', jid, s.dumps(job),
                    job['createdAt'], job['updatedAt']))
    (s.job_directory(jid) / attempt / 'staging').mkdir(parents=True)
    return job


@pytest.mark.parametrize('operation', ['generate_video', 'process_video', 'apply_follow'])
def test_empty_clips_fail_without_publishing_database_changes(project, monkeypatch, operation):
    job = make_job(project, operation)
    if operation == 'apply_follow':
        from services.worker import clip_tools_task
        monkeypatch.setattr(clip_tools_task, 'publish_follow', lambda *args: None)
    before_job = s.get_job(job['jobId'])
    before_project = s.get_project(project['projectId'])
    with s.connect() as db:
        revisions = db.execute('SELECT count(*) FROM revisions WHERE project_id=?', (project['projectId'],)).fetchone()[0]
        artifacts = db.execute('SELECT count(*) FROM artifacts WHERE job_id=?', (job['jobId'],)).fetchone()[0]

    with pytest.raises(s.AppError) as error:
        publish(job, {'ok': True, 'result': {'files': [], 'clips': []}})

    assert error.value.code == 'LIBRARY_PUBLICATION_INCOMPLETE'
    assert s.get_project(project['projectId']) == before_project
    assert s.get_job(job['jobId']) == before_job
    with s.connect() as db:
        assert db.execute('SELECT count(*) FROM revisions WHERE project_id=?', (project['projectId'],)).fetchone()[0] == revisions
        assert db.execute('SELECT count(*) FROM artifacts WHERE job_id=?', (job['jobId'],)).fetchone()[0] == artifacts
