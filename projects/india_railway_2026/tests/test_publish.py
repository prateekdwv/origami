"""Publish audited exports and retain the previous video when auditing fails."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import schedule_render


class PublishTests(unittest.TestCase):
    def publish(self, succeeds):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)/'2026-10-15'
            directory.mkdir()
            video = directory/'SCHEDULED_TEST.mp4'
            video.write_bytes(b'previous verified video')
            report = directory/'verification.json'
            report.write_text('{"passed": true}')
            (directory/'preview_dataset.json.gz').write_bytes(b'fixture cache')
            data = {"journeys": [{}], "coverage": {"selected": 1}}
            def encode(data, path, compose, **options):
                path.write_bytes(b'new unverified video')
                return {}
            with patch.object(schedule_render, 'OUTPUT', Path(folder)), \
                 patch.object(schedule_render, 'cache_matches', return_value=True), \
                 patch.object(schedule_render, 'read_gzip', return_value=data), \
                 patch.object(schedule_render, 'update_categories', return_value=False), \
                 patch('sys.argv', ['schedule_render.py']), \
                 patch('replay.validate'), patch('replay.export_stills'), \
                 patch('replay.render_video', side_effect=encode), \
                 patch('replay.verify', side_effect=None if succeeds else RuntimeError('audit failed'),
                       return_value={"passed": True, "status": "passed", "frames_compared": 1}), \
                 patch('design.FrameRenderer'), \
                 patch('design.traffic_series', return_value=(np.array([0]), np.array([1]))):
                if succeeds:
                    schedule_render.main()
                else:
                    with self.assertRaisesRegex(RuntimeError, 'audit failed'):
                        schedule_render.main()
            self.assertEqual(video.read_bytes(), b'new unverified video' if succeeds else b'previous verified video')
            self.assertTrue(json.loads(report.read_text())['passed'])
            self.assertEqual(sorted(p.name for p in directory.iterdir()),
                             sorted(['SCHEDULED_TEST.mp4', 'preview_dataset.json.gz', 'verification.json']
                                    + (['coverage.json'] if succeeds else [])))

    def test_failed_audit_keeps_previous_video_and_report(self):
        self.publish(False)

    def test_successful_export_publishes_content_and_cleans_staging(self):
        self.publish(True)

    def test_final_reuses_cache_and_requests_higher_quality_and_full_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cache = root/'scheduled_test'/'2026-10-15'
            cache.mkdir(parents=True)
            prepared = cache/'preview_dataset.json.gz'
            prepared.write_bytes(b'unchanged cache')
            data = {"journeys": [{}], "coverage": {"selected": 1}}
            def encode(data, path, compose, **options):
                path.write_bytes(b'final movie')
                return {}
            with patch.object(schedule_render, 'MEDIA', root), \
                 patch.object(schedule_render, 'OUTPUT', root/'scheduled_test'), \
                 patch.object(schedule_render, 'cache_matches', return_value=True), \
                 patch.object(schedule_render, 'read_gzip', return_value=data), \
                 patch.object(schedule_render, 'update_categories', return_value=False), \
                 patch('sys.argv', ['schedule_render.py', '--final']), \
                 patch('replay.validate'), patch('replay.export_stills'), \
                 patch('replay.render_video', side_effect=encode) as render, \
                 patch('replay.verify', return_value={"passed": True, "status": "passed", "frames_compared": 1800}) as audit, \
                 patch('design.FrameRenderer'), \
                 patch('design.traffic_series', return_value=(np.array([0]), np.array([1]))):
                schedule_render.main()
            self.assertEqual(render.call_args.kwargs['crf'], 18)
            self.assertTrue(audit.call_args.kwargs['full'])
            self.assertEqual(prepared.read_bytes(), b'unchanged cache')
            final = root/'final'/'2026-10-15'
            self.assertEqual((final/'India_Railways_2026-10-15.mp4').read_bytes(), b'final movie')
            self.assertFalse((final/'preview_dataset.json.gz').exists())
