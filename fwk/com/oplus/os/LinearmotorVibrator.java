/*
 * Copyright (C) 2022 The Nameless-AOSP Project
 * SPDX-License-Identifier: Apache-2.0
 */

package com.oplus.os;

/**
 * Only resolves the type: a ROM that needs this jar has no "linearmotor"
 * service, so the camera never gets an instance.
 */
public class LinearmotorVibrator {
    public void vibrate(WaveformEffect effect) {
    }
}
