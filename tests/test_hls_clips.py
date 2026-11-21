import json
import subprocess
from types import SimpleNamespace

import pytest

import hls_clips


def test_playlist_rejects_remote_and_encrypted_media():
    good = '#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:2\nseg.m4s\n#EXT-X-ENDLIST\n'
    assert hls_clips.playlist_files(good) == {'init.mp4', 'seg.m4s'}
    for bad in [good.replace('seg.m4s', 'https://evil.test/a'),
                good.replace('seg.m4s', '../outside'),
                good.replace('#EXTINF', '#EXT-X-KEY:METHOD=AES-128\n#EXTINF'),
                good.replace('#EXT-X-ENDLIST', ''),
                good.replace('#EXTINF', '#EXT-X-PART:URI="/etc/passwd"\n#EXTINF'),
                good.replace('URI="init.mp4"', 'URI="../secret"')]:
        with pytest.raises(ValueError):
            hls_clips.playlist_files(bad)


def test_download_localized_uses_only_local_ffmpeg_inputs(monkeypatch, tmp_path):
    requests = []
    def read(url, limit):
        requests.append(url)
        if url.endswith('info.json'):
            return json.dumps({'hls_exists': True, 'imdb': 'tt12345', 'audio_languages': ['ja']}).encode()
        if url.endswith('.m3u8'):
            media = 'v.m4s' if 'video-' in url else 'a.m4s'
            return f'#EXTM3U\n#EXTINF:1\n{media}\n#EXT-X-ENDLIST\n'.encode()
        return b'part'
    monkeypatch.setattr(hls_clips, '_read', read)
    def ffmpeg(args, **kwargs):
        assert 'file' in args
        assert not any('https:' in part for part in args)
        (tmp_path / 'out.mp4').write_bytes(b'0000ftyp' + b'x' * 1100)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(hls_clips.subprocess, 'run', ffmpeg)
    assert hls_clips.download_localized('hello', 'ja', tmp_path / 'out.mp4')
    assert any('audio-ja.m3u8' in url for url in requests)


def test_missing_audio_track_never_builds_mp4(monkeypatch, tmp_path):
    monkeypatch.setattr(hls_clips, '_read', lambda *args: b'{"hls_exists":true,"imdb":"tt123","audio_languages":["en"]}')
    assert not hls_clips.download_localized('hello', 'hi', tmp_path / 'out.mp4')
    assert not (tmp_path / 'out.mp4').exists()


def test_bundled_ffmpeg_muxes_localized_hls_without_system_tools(monkeypatch, tmp_path):
    import imageio_ffmpeg

    import media_tools
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    origin = tmp_path / 'origin'
    origin.mkdir()
    def create(input_spec, extra, playlist, init, segments):
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', input_spec, '-t', '2', *extra,
                        '-f', 'hls', '-hls_time', '1', '-hls_segment_type', 'fmp4',
                        '-hls_fmp4_init_filename', init, '-hls_segment_filename', str(origin / segments),
                        str(origin / playlist)], check=True, capture_output=True, timeout=30)
    create('color=c=black:s=64x64:r=5', ['-c:v', 'libx264', '-pix_fmt', 'yuv420p'], 'video-lq.m3u8', 'init-video.mp4', 'video-%d.m4s')
    create('sine=frequency=440:sample_rate=44100', ['-c:a', 'aac'], 'audio-ja.m3u8', 'init-audio.mp4', 'audio-%d.m4s')
    def read(url, limit):
        if url.endswith('info.json'):
            return json.dumps({'hls_exists': True, 'imdb': 'tt123', 'audio_languages': ['ja']}).encode()
        data = (origin / url.rsplit('/', 1)[-1]).read_bytes()
        assert len(data) <= limit
        return data
    monkeypatch.setattr(hls_clips, '_read', read)
    monkeypatch.setattr(media_tools.shutil, 'which', lambda name: None)
    result = tmp_path / 'localized.mp4'
    assert hls_clips.download_localized('sample', 'ja', result)
    assert result.stat().st_size > 1024
