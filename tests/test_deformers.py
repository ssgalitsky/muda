#!/usr/bin/env python

from copy import deepcopy
import re
import six

import numpy as np
import soundfile as psf

import jams
import librosa

import muda

import pytest


def ap_(a, b, msg=None, rtol=1e-5, atol=1e-5):
    """Shorthand for 'assert np.allclose(a, b, rtol, atol), "%r != %r" % (a, b)
    """
    if not np.allclose(a, b, rtol=rtol, atol=atol):
        raise AssertionError(msg or "{} != {}".format(a, b))


@pytest.fixture(scope='module')
def jam_fixture():
    return muda.load_jam_audio('tests/data/fixture.jams',
                               'tests/data/fixture.wav')


@pytest.fixture(scope='module')
def jam_raw():
    return jams.load('tests/data/fixture.jams')


@pytest.mark.xfail(raises=RuntimeError)
def test_raw(jam_raw):

    D = muda.deformers.TimeStretch(rate=2.0)
    six.next(D.transform(jam_raw))


def __test_time(jam_orig, jam_new, rate):

    # Test the track length
    ap_(librosa.get_duration(**jam_orig.sandbox.muda['_audio']),
        rate * librosa.get_duration(**jam_new.sandbox.muda['_audio']))

    # Test the metadata
    ap_(jam_orig.file_metadata.duration,
        rate * jam_new.file_metadata.duration)

    # Test each annotation
    for ann_orig, ann_new in zip(jam_orig.annotations, jam_new.annotations):
        # JAMS 0.2.1 support
        if hasattr(ann_orig, 'time'):
            ap_(ann_orig.time, rate * ann_new.time)
            ap_(ann_orig.duration, rate * ann_new.duration)

        assert len(ann_orig.data) == len(ann_new.data)

        for obs1, obs2 in zip(ann_orig, ann_new):

            ap_(obs1.time, rate * obs2.time)
            ap_(obs1.duration, rate * obs2.duration)

            if ann_orig.namespace == 'tempo':
                ap_(rate * obs1.value, obs2.value)


def __test_deformer_history(deformer, history):

    d_trans = history['transformer']
    params = deformer.get_params()

    assert d_trans['params'] == params['params']
    assert d_trans['__class__'] == params['__class__'].__name__


@pytest.mark.parametrize('rate', [0.5, 1.0, 2.0, [1.0, 1.5],
                                  pytest.mark.xfail(-1, raises=ValueError),
                                  pytest.mark.xfail(-0.5, raises=ValueError),
                                  pytest.mark.xfail(0.0, raises=ValueError)])
def test_timestretch(rate, jam_fixture):

    D = muda.deformers.TimeStretch(rate=rate)

    jam_orig = deepcopy(jam_fixture)

    for jam_new in D.transform(jam_orig):
        # Verify that the original jam reference hasn't changed
        assert jam_new is not jam_fixture
        __test_time(jam_orig, jam_fixture, 1.0)

        # Verify that the state and history objects are intact
        __test_deformer_history(D, jam_new.sandbox.muda.history[-1])

        d_state = jam_new.sandbox.muda.history[-1]['state']
        d_rate = d_state['rate']
        if isinstance(rate, list):
            assert d_rate in rate
        else:
            assert d_rate == rate

        __test_time(jam_orig, jam_new, d_rate)

    # Serialization test
    D2 = muda.deserialize(muda.serialize(D))
    assert D.get_params() == D2.get_params()


@pytest.fixture(params=[1, 3, 5,
                        pytest.mark.xfail(-3, raises=ValueError),
                        pytest.mark.xfail(0, raises=ValueError)])
def n_samples(request):
    return request.param


@pytest.mark.parametrize('lower, upper',
                         [(-1, 0.5), (0.0, 1.0),
                          pytest.mark.xfail((-1, -3), raises=ValueError),
                          pytest.mark.xfail((2, 1), raises=ValueError)])
def test_log_timestretch(n_samples, lower, upper, jam_fixture):

    D = muda.deformers.LogspaceTimeStretch(n_samples=n_samples,
                                           lower=lower,
                                           upper=upper)

    jam_orig = deepcopy(jam_fixture)

    n_out = 0
    for jam_new in D.transform(jam_orig):
        # Verify that the original jam reference hasn't changed
        assert jam_new is not jam_fixture
        __test_time(jam_orig, jam_fixture, 1.0)

        # Verify that the state and history objects are intact
        __test_deformer_history(D, jam_new.sandbox.muda.history[-1])

        d_state = jam_new.sandbox.muda.history[-1]['state']
        d_rate = d_state['rate']
        assert 2.0**lower <= d_rate <= 2.0**upper

        __test_time(jam_orig, jam_new, d_rate)
        n_out += 1

    assert n_samples == n_out
    # Serialization test
    D2 = muda.deserialize(muda.serialize(D))
    assert D.get_params() == D2.get_params()


@pytest.mark.parametrize('scale',
                         [0.1,
                          pytest.mark.xfail(0, raises=ValueError),
                          pytest.mark.xfail(-1, raises=ValueError)])
def test_random_timestretch(n_samples, scale, jam_fixture):

    np.random.seed(0)
    D = muda.deformers.RandomTimeStretch(n_samples=n_samples, scale=scale)

    jam_orig = deepcopy(jam_fixture)

    n_out = 0
    for jam_new in D.transform(jam_orig):
        # Verify that the original jam reference hasn't changed
        assert jam_new is not jam_orig
        __test_time(jam_orig, jam_fixture, 1.0)

        # Verify that the state and history objects are intact
        __test_deformer_history(D, jam_new.sandbox.muda.history[-1])

        d_state = jam_new.sandbox.muda.history[-1]['state']
        d_rate = d_state['rate']

        __test_time(jam_orig, jam_new, d_rate)
        n_out += 1

    assert n_samples == n_out
    # Serialization test
    D2 = muda.deserialize(muda.serialize(D))
    assert D.get_params() == D2.get_params()


@pytest.fixture(scope='module',
                params=[0.5,
                        pytest.mark.xfail(None, raises=TypeError)])
def D_simple(request):
    if request.param is None:
        return None
    else:
        return muda.deformers.TimeStretch(rate=request.param)


def test_bypass(D_simple, jam_fixture):

    D = muda.deformers.Bypass(transformer=D_simple)

    jam_orig = deepcopy(jam_fixture)

    generator = D.transform(jam_orig)
    jam_new = six.next(generator)
    assert jam_new is jam_orig
    __test_time(jam_orig, jam_fixture, 1.0)

    for jam_new in generator:
        # Verify that the original jam reference hasn't changed
        assert jam_new is not jam_orig

        # Verify that the state and history objects are intact
        __test_deformer_history(D_simple, jam_new.sandbox.muda.history[-1])
    # Serialization test
    D2 = muda.deserialize(muda.serialize(D))
    assert D.get_params() == D2.get_params()


def pstrip(x):

    root = re.match(six.text_type('([A-G][b#]*).*'),
                    six.text_type(x)).groups()[0]

    return librosa.note_to_midi(root)


def __test_note(ann_orig, ann_new, n):

    for obs1, obs2 in zip(ann_orig, ann_new):
        v_orig = pstrip(obs1.value)
        v_new = pstrip(obs2.value)
        v_orig = np.mod(np.round(np.mod(v_orig + n, 12)), 12)
        v_new = np.mod(np.round(np.mod(v_new, 12)), 12)
        ap_(v_orig, v_new)


def __test_tonic(ann_orig, ann_new, n):

    for obs1, obs2 in zip(ann_orig, ann_new):
        v_orig = pstrip(obs1.value['tonic'])
        v_new = pstrip(obs2.value['tonic'])

        v_orig = np.mod(np.round(np.mod(v_orig + n, 12)), 12)
        v_new = np.mod(np.round(np.mod(v_new, 12)), 12)
        ap_(v_orig, v_new)


def __test_contour(ann_orig, ann_new, n):

    scale = 2.0**(float(n) / 12)

    for obs1, obs2 in zip(ann_orig, ann_new):
        ap_(obs1.value['frequency'] * scale, obs2.value['frequency'])


def __test_hz(ann_orig, ann_new, n):

    scale = 2.0**(float(n) / 12)

    for obs1, obs2 in zip(ann_orig, ann_new):
        ap_(obs1.value * scale, obs2.value)


def __test_midi(ann_orig, ann_new, n):

    for obs1, obs2 in zip(ann_orig, ann_new):
        ap_(obs1.value + n, obs2.value)


def __test_pitch(jam_orig, jam_new, n_semitones, tuning):

    if -0.5 < tuning + n_semitones <= 0.5:
        q_tones = 0.0
    else:
        q_tones = n_semitones

    # Test each annotation
    for ann_orig, ann_new in zip(jam_orig.annotations, jam_new.annotations):
        assert len(ann_orig) == len(ann_new)

        if ann_orig.namespace in ['chord', 'chord_harte', 'key_mode']:
            __test_note(ann_orig, ann_new, q_tones)
        elif ann_orig.namespace in ['pitch_class', 'chord_roman']:
            __test_tonic(ann_orig, ann_new, q_tones)
        elif ann_orig.namespace == 'pitch_contour':
            __test_contour(ann_orig, ann_new, n_semitones)
        elif ann_orig.namespace == 'pitch_hz':
            __test_hz(ann_orig, ann_new, n_semitones)
        elif ann_orig.namespace == 'pitch_midi':
            __test_midi(ann_orig, ann_new, n_semitones)


@pytest.mark.parametrize('n_semitones',
                         [-2, -1, -0.5, -0.25, 0, 0.25, 1.0, 1.5, [-1, 1]])
def test_pitchshift(n_semitones, jam_fixture):
    np.random.seed(0)
    D = muda.deformers.PitchShift(n_semitones=n_semitones)

    jam_orig = deepcopy(jam_fixture)

    for jam_new in D.transform(jam_orig):
        # Verify that the original jam reference hasn't changed
        assert jam_new is not jam_orig
        __test_pitch(jam_orig, jam_fixture, 0.0, 0)

        # Verify that the state and history objects are intact
        __test_deformer_history(D, jam_new.sandbox.muda.history[-1])

        d_state = jam_new.sandbox.muda.history[-1]['state']
        d_tones = d_state['n_semitones']
        tuning = d_state['tuning']
        if isinstance(n_semitones, list):
            assert d_tones in n_semitones
        else:
            assert d_tones == n_semitones

        __test_pitch(jam_orig, jam_new, d_tones, tuning)
    # Serialization test
    D2 = muda.deserialize(muda.serialize(D))
    assert D.get_params() == D2.get_params()


@pytest.mark.parametrize('sigma',
                         [0.5,
                          pytest.mark.xfail(-1, raises=ValueError),
                          pytest.mark.xfail(0, raises=ValueError)])
def test_random_pitchshift(n_samples, sigma, jam_fixture):

    D = muda.deformers.RandomPitchShift(n_samples=n_samples, sigma=sigma)

    jam_orig = deepcopy(jam_fixture)

    n_out = 0
    for jam_new in D.transform(jam_orig):
        # Verify that the original jam reference hasn't changed
        assert jam_new is not jam_orig
        __test_pitch(jam_orig, jam_fixture, 0.0, 0.0)

        # Verify that the state and history objects are intact
        __test_deformer_history(D, jam_new.sandbox.muda.history[-1])

        d_state = jam_new.sandbox.muda.history[-1]['state']
        d_tones = d_state['n_semitones']
        tuning = d_state['tuning']
        __test_pitch(jam_orig, jam_new, d_tones, tuning)
        n_out += 1

    assert n_out == n_samples
    # Serialization test
    D2 = muda.deserialize(muda.serialize(D))
    assert D.get_params() == D2.get_params()


@pytest.mark.parametrize('lower, upper',
                         [(-3, 1), (0.0, 3.0),
                          pytest.mark.xfail((-1, -3), raises=ValueError),
                          pytest.mark.xfail((2, 1), raises=ValueError)])
def test_linear_pitchshift(n_samples, lower, upper, jam_fixture):
    D = muda.deformers.LinearPitchShift(n_samples=n_samples,
                                        lower=lower,
                                        upper=upper)

    jam_orig = deepcopy(jam_fixture)

    n_out = 0
    for jam_new in D.transform(jam_orig):
        # Verify that the original jam reference hasn't changed
        assert jam_new is not jam_orig
        __test_pitch(jam_orig, jam_fixture, 0.0, 0.0)

        # Verify that the state and history objects are intact
        __test_deformer_history(D, jam_new.sandbox.muda.history[-1])

        d_state = jam_new.sandbox.muda.history[-1]['state']
        d_tones = d_state['n_semitones']
        tuning = d_state['tuning']
        assert lower <= d_tones <= upper

        __test_pitch(jam_orig, jam_new, d_tones, tuning)
        n_out += 1

    assert n_out == n_samples
    # Serialization test
    D2 = muda.deserialize(muda.serialize(D))
    assert D.get_params() == D2.get_params()


def __test_effect(jam_orig, jam_new):
    for ann_orig, ann_new in zip(jam_orig.annotations, jam_new.annotations):
        assert ann_orig == ann_new


@pytest.fixture(params=[p for p in muda.deformers.sox.PRESETS] +
                list(muda.deformers.sox.PRESETS.keys()))
def preset(request):
    return request.param


def test_drc(preset, jam_fixture):

    D = muda.deformers.DynamicRangeCompression(preset=preset)

    jam_orig = deepcopy(jam_fixture)

    for jam_new in D.transform(jam_orig):

        assert jam_new is not jam_fixture
        __test_effect(jam_orig, jam_fixture)

        assert not np.allclose(jam_orig.sandbox.muda['_audio']['y'],
                               jam_new.sandbox.muda['_audio']['y'])

        __test_effect(jam_orig, jam_new)
    # Serialization test
    D2 = muda.deserialize(muda.serialize(D))
    assert D.get_params() == D2.get_params()


@pytest.mark.parametrize('noise', ['tests/data/noise_sample.ogg',
                                   ['tests/data/noise_sample.ogg']])
@pytest.mark.parametrize('weight_min, weight_max',
                         [(0.01, 0.6), (0.1, 0.8), (0.5, 0.99),
                          pytest.mark.xfail((0.0, 0.5), raises=ValueError),
                          pytest.mark.xfail((-1, 0.5), raises=ValueError),
                          pytest.mark.xfail((0.5, 1.5), raises=ValueError),
                          pytest.mark.xfail((0.75, 0.25), raises=ValueError)])
def test_background(noise, n_samples, weight_min, weight_max, jam_fixture):

    D = muda.deformers.BackgroundNoise(files=noise,
                                       n_samples=n_samples,
                                       weight_min=weight_min,
                                       weight_max=weight_max)

    jam_orig = deepcopy(jam_fixture)
    orig_duration = librosa.get_duration(**jam_orig.sandbox.muda['_audio'])

    n_out = 0
    for jam_new in D.transform(jam_orig):

        assert jam_new is not jam_fixture
        __test_effect(jam_orig, jam_fixture)

        assert not np.allclose(jam_orig.sandbox.muda['_audio']['y'],
                               jam_new.sandbox.muda['_audio']['y'])

        d_state = jam_new.sandbox.muda.history[-1]['state']
        filename = d_state['filename']
        start = d_state['start']
        stop = d_state['stop']

        with psf.SoundFile(str(filename), mode='r') as soundf:
            max_index = len(soundf)
            noise_sr = soundf.samplerate

        assert 0 <= start < stop
        assert start < stop <= max_index
        assert ((stop - start) / float(noise_sr)) == orig_duration

        __test_effect(jam_orig, jam_new)
        n_out += 1

    assert n_out == n_samples
    # Serialization test
    D2 = muda.deserialize(muda.serialize(D))
    assert D.get_params() == D2.get_params()


@pytest.mark.xfail(raises=RuntimeError)
def test_background_no_file():
    muda.deformers.BackgroundNoise(files='does-not-exist.ogg', n_samples=1)


@pytest.mark.xfail(raises=RuntimeError)
def test_background_short_file():
    D = muda.deformers.BackgroundNoise(files='tests/data/fixture.wav')
    jam_orig = muda.load_jam_audio('tests/data/fixture.jams',
                                   'tests/data/noise_sample.ogg')
    jam_new = next(D.transform(jam_orig))


def test_pipeline(jam_fixture):
    D1 = muda.deformers.TimeStretch(rate=2.0)
    D2 = muda.deformers.TimeStretch(rate=1.5)

    P = muda.Pipeline([('stretch_1', D1),
                       ('stretch_2', D2)])

    jam_orig = deepcopy(jam_fixture)

    for jam_new in P.transform(jam_orig):
        assert jam_new is not jam_orig
        __test_time(jam_orig, jam_fixture, 1.0)

        # Verify that the state and history objects are intact
        __test_deformer_history(D1, jam_new.sandbox.muda.history[0])
        __test_deformer_history(D2, jam_new.sandbox.muda.history[-1])

        __test_time(jam_orig, jam_new, D1.rate[0] * D2.rate[0])


def test_union(jam_fixture):
    D1 = muda.deformers.TimeStretch(rate=[1.0, 2.0, 3.0])
    D2 = muda.deformers.TimeStretch(rate=[0.5, 1.5, 2.5])

    rates = [1.0, 0.5, 2.0, 1.5, 3.0, 2.5]

    union = muda.Union([('stretch_1', D1),
                        ('stretch_2', D2)])

    jam_orig = deepcopy(jam_fixture)

    for i, jam_new in enumerate(union.transform(jam_orig)):
        assert jam_new is not jam_orig
        __test_time(jam_orig, jam_fixture, 1.0)

        # Verify that the state and history objects are intact
        if i % 2:
            __test_deformer_history(D2, jam_new.sandbox.muda.history[-1])
        else:
            __test_deformer_history(D1, jam_new.sandbox.muda.history[-1])

        __test_time(jam_orig, jam_new, rates[i])


@pytest.mark.xfail(raises=ValueError)
def test_bad_pipeline_unique():
    D1 = muda.deformers.TimeStretch(rate=2.0)
    D2 = muda.deformers.TimeStretch(rate=1.5)

    muda.Pipeline([('stretch', D1), ('stretch', D2)])


@pytest.mark.xfail(raises=ValueError)
def test_bad_union_unique():
    D1 = muda.deformers.TimeStretch(rate=2.0)
    D2 = muda.deformers.TimeStretch(rate=1.5)

    muda.Union([('stretch', D1), ('stretch', D2)])


@pytest.mark.xfail(raises=TypeError)
def test_bad_pipeline_object():
    D = muda.deformers.TimeStretch(rate=2.0)

    muda.Pipeline([('stretch1', D),
                   ('stretch2', 'not a basetransformer')])


@pytest.mark.xfail(raises=TypeError)
def test_bad_union_object():
    D = muda.deformers.TimeStretch(rate=2.0)

    muda.Union([('stretch1', D),
                ('stretch2', 'not a basetransformer')])


@pytest.mark.xfail(raises=NotImplementedError)
def test_base_transformer():

    D = muda.BaseTransformer()

    six.next(D.transform(jam_fixture))
