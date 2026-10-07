.method public getSurfaceSize(Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;I)Ljava/util/List;
    .locals 10

    # Keep the original result for all unaffected surfaces and modes.
    invoke-virtual/range {p0 .. p5}, Lcom/oplus/ocs/camera/producer/mode/PhotoMode;->getOriginalSurfaceSize(Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;I)Ljava/util/List;
    move-result-object v9

    const-string v0, "reprocess_yuv"
    invoke-virtual {v0, p2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-eqz v0, :original
    const-string v0, "rear_sat"
    invoke-virtual {v0, p3}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-eqz v0, :original

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
    if-ne v1, v2, :original

    # The processing stream belongs to the logical camera, rather than the
    # largest physical lens. Retain a real square buffer and saved aspect ratio.
    move-object v0, p3
    const-wide/high16 v1, 0x3ff0000000000000L
    const/16 v3, 0x23
    invoke-static {v0, v1, v2, v3}, Lcom/oplus/ocs/camera/producer/info/CameraCharacteristicsHelper;->getSizeByFormat(Ljava/lang/String;DI)Landroid/util/Size;
    move-result-object v4
    if-eqz v4, :original
    invoke-virtual {v4}, Landroid/util/Size;->getWidth()I
    move-result v5
    invoke-virtual {v4}, Landroid/util/Size;->getHeight()I
    move-result v6
    if-ne v5, v6, :original
    if-lez v5, :original
    new-instance v0, Landroid/util/Pair;
    invoke-direct {v0, v4, v4}, Landroid/util/Pair;-><init>(Ljava/lang/Object;Ljava/lang/Object;)V
    invoke-static {v0}, Ljava/util/Collections;->singletonList(Ljava/lang/Object;)Ljava/util/List;
    move-result-object v9

    :original
    return-object v9
.end method
