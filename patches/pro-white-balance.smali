.method private checkColorTemperature(Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;)V
    .locals 5

    # CamX needs AWB running to apply the manual colour-temperature override.
    # AWB_OFF bypasses that algorithm and leaves the preview's gains unchanged.
    sget-object v0, Landroid/hardware/camera2/CaptureRequest;->CONTROL_AWB_MODE:Landroid/hardware/camera2/CaptureRequest$Key;
    const/4 v1, 0x1
    invoke-static {v1}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;
    move-result-object v2
    invoke-virtual {p1, v0, v2}, Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;->set(Landroid/hardware/camera2/CaptureRequest$Key;Ljava/lang/Object;)Lcom/oplus/ocs/camera/metadata/parameter/Parameter$BaseBuilder;

    sget-object v0, Lcom/oplus/ocs/camera/metadata/URequestKeys;->KEY_COLOR_TEMPERATURE:Lcom/oplus/ocs/camera/metadata/PreviewKey;
    invoke-virtual {p1, v0}, Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;->get(Lcom/oplus/ocs/camera/metadata/RequestKey;)Ljava/lang/Object;
    move-result-object v0
    check-cast v0, [I
    const/4 v2, 0x0
    if-eqz v0, :auto_wb
    array-length v3, v0
    if-eqz v3, :auto_wb
    aget v3, v0, v2
    if-lez v3, :auto_wb

    new-instance v3, Landroid/hardware/camera2/CaptureRequest$Key;
    const-string v4, "org.codeaurora.qcamera3.manualWB.color_temperature"
    const-class p0, [I
    invoke-direct {v3, v4, p0}, Landroid/hardware/camera2/CaptureRequest$Key;-><init>(Ljava/lang/String;Ljava/lang/Class;)V
    invoke-virtual {p1, v3, v0}, Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;->set(Landroid/hardware/camera2/CaptureRequest$Key;Ljava/lang/Object;)Lcom/oplus/ocs/camera/metadata/parameter/Parameter$BaseBuilder;
    const/4 v2, 0x1

    :auto_wb
    new-instance v3, Landroid/hardware/camera2/CaptureRequest$Key;
    const-string v4, "org.codeaurora.qcamera3.manualWB.partial_mwb_mode"
    const-class p0, [I
    invoke-direct {v3, v4, p0}, Landroid/hardware/camera2/CaptureRequest$Key;-><init>(Ljava/lang/String;Ljava/lang/Class;)V
    filled-new-array {v2}, [I
    move-result-object v0
    invoke-virtual {p1, v3, v0}, Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;->set(Landroid/hardware/camera2/CaptureRequest$Key;Ljava/lang/Object;)Lcom/oplus/ocs/camera/metadata/parameter/Parameter$BaseBuilder;
    return-void
.end method
