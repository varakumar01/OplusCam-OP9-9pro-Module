.method public getSurfaceSize(Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;I)Ljava/util/List;
    .locals 10

    invoke-virtual/range {p0 .. p5}, Lcom/oplus/ocs/camera/producer/mode/PhotoMode;->getOriginalSurfaceSize(Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;I)Ljava/util/List;
    move-result-object v9

    const-string v0, "reprocess_yuv"
    invoke-virtual {v0, p2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-nez v0, :logical_check
    const-string v0, "capture_yuv"
    invoke-virtual {v0, p2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-eqz v0, :original
    const-string v0, "rear_main"
    invoke-virtual {v0, p3}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-nez v0, :ratio_checks
    const-string v0, "rear_wide"
    invoke-virtual {v0, p3}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-nez v0, :ratio_checks
    const-string v0, "rear_tele"
    invoke-virtual {v0, p3}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-eqz v0, :original
    goto :ratio_checks
    :logical_check
    const-string v0, "rear_sat"
    invoke-virtual {v0, p3}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-eqz v0, :original

    :ratio_checks
    # Quick recording retains its own session sizing.
    iget-boolean v0, p0, Lcom/oplus/ocs/camera/producer/mode/PhotoMode;->mbQuickVideoRecording:Z
    if-nez v0, :original

    # This trial handles ordinary YUV only, not Hi-res or ten-bit capture.
    invoke-virtual {p0, p4}, Lcom/oplus/ocs/camera/producer/mode/PhotoMode;->is10BitOpen(Ljava/lang/String;)Z
    move-result v0
    if-nez v0, :original
    invoke-virtual {p0, p4}, Lcom/oplus/ocs/camera/producer/mode/PhotoMode;->getConfigureParameter(Ljava/lang/String;)Lcom/oplus/ocs/camera/metadata/parameter/Parameter;
    move-result-object v0
    if-eqz v0, :original
    sget-object v1, Lcom/oplus/ocs/camera/metadata/UConfigureKeys;->HIGH_PICTURE_SIZE_ENABLE:Lcom/oplus/ocs/camera/metadata/ConfigureKey;
    invoke-virtual {v0, v1}, Lcom/oplus/ocs/camera/metadata/parameter/Parameter;->get(Lcom/oplus/ocs/camera/metadata/RequestKey;)Ljava/lang/Object;
    move-result-object v0
    const-string v1, "on"
    invoke-virtual {v1, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-nez v0, :original

    iget-object v0, p0, Lcom/oplus/ocs/camera/producer/mode/PhotoMode;->mTagMap:Ljava/util/Map;
    if-eqz v0, :original
    invoke-interface {v0, p4}, Ljava/util/Map;->get(Ljava/lang/Object;)Ljava/lang/Object;
    move-result-object v0
    check-cast v0, Lcom/oplus/ocs/camera/common/util/ApsRequestTag;
    if-eqz v0, :original
    iget-object v0, v0, Lcom/oplus/ocs/camera/common/util/ApsRequestTag;->mPreviewSize:Landroid/util/Size;
    if-eqz v0, :original
    invoke-virtual {v0}, Landroid/util/Size;->getWidth()I
    move-result v1
    invoke-virtual {v0}, Landroid/util/Size;->getHeight()I
    move-result v2
    if-lez v1, :original
    if-lez v2, :original
    int-to-double v3, v1
    int-to-double v5, v2
    div-double v1, v3, v5

    # Retain the working 4:3 path. Use the same aspect as the original method.
    const-wide v3, 0x3ff5555555555555L
    sub-double v3, v1, v3
    invoke-static {v3, v4}, Ljava/lang/Math;->abs(D)D
    move-result-wide v3
    const-wide v5, 0x3f947ae147ae147bL    # 0.02
    cmpg-double v7, v3, v5
    if-lez v7, :original

    # Choose an advertised YUV output for this stream's camera. Custom JPEG
    # dimensions are not necessarily valid physical or logical YUV outputs.
    # Keep the requested aspect; do not fabricate a missing output size.
    move-object v0, p3
    const/16 v3, 0x23
    invoke-static {v0, v1, v2, v3}, Lcom/oplus/ocs/camera/producer/info/CameraCharacteristicsHelper;->getSizeByFormat(Ljava/lang/String;DI)Landroid/util/Size;
    move-result-object v8
    if-eqz v8, :original
    invoke-virtual {v8}, Landroid/util/Size;->getWidth()I
    move-result v5
    invoke-virtual {v8}, Landroid/util/Size;->getHeight()I
    move-result v6
    if-lez v5, :original
    if-lez v6, :original
    int-to-double v3, v5
    int-to-double v5, v6
    div-double/2addr v3, v5
    sub-double/2addr v3, v1
    invoke-static {v3, v4}, Ljava/lang/Math;->abs(D)D
    move-result-wide v3
    const-wide v5, 0x3f947ae147ae147bL
    cmpg-double v7, v3, v5
    if-gtz v7, :original

    new-instance v0, Landroid/util/Pair;
    invoke-direct {v0, v8, v8}, Landroid/util/Pair;-><init>(Ljava/lang/Object;Ljava/lang/Object;)V
    invoke-static {v0}, Ljava/util/Collections;->singletonList(Ljava/lang/Object;)Ljava/util/List;
    move-result-object v9

    :original
    return-object v9
.end method
