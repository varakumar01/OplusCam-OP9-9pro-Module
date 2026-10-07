# Applied only with the paired, source-pinned LOG graphics trial.
# Keep native LOG processing, but avoid the stalled LOG + Film EIS session.
.method private final ooscameraGuardFilmOptions(Lp6/a;Ljava/lang/Object;)V
    .locals 4

    const-string v0, "on"
    invoke-virtual {v0, p2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v1
    if-eqz v1, :done

    iget-object v1, p1, Lp6/a;->f:Ljava/lang/String;
    const-string v2, "pref_film_video_log"
    invoke-virtual {v2, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v2
    if-eqz v2, :check_eis
    sget-object v2, Lr6/g;->k:Lp6/a;
    # Film EIS defaults to on, even when no value has been saved.
    move-object v3, v0
    goto :check_other

    :check_eis
    const-string v2, "pref_film_video_eis_menu"
    invoke-virtual {v2, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v2
    if-eqz v2, :done
    sget-object v2, Lr6/g;->o:Lp6/a;
    const-string v3, "off"

    :check_other
    invoke-virtual {p0, v2, v3}, Lcom/oplus/camera/data/DataManager;->a(Lp6/a;Ljava/lang/Object;)Ljava/lang/Object;
    move-result-object v1
    invoke-virtual {v0, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v1
    if-eqz v1, :done

    # Normal notification updates both the UI and the camera session.
    # The recursive setter receives off and exits this guard immediately.
    const-string v1, "off"
    invoke-virtual {p0, v2, v1}, Lcom/oplus/camera/data/DataManager;->f(Lp6/a;Ljava/lang/Object;)V
    new-instance v1, Lcom/oplus/camera/data/OosCameraFilmNotice;
    invoke-direct {v1}, Lcom/oplus/camera/data/OosCameraFilmNotice;-><init>()V
    invoke-static {v1}, Ly5/o;->e(Ljava/lang/Runnable;)V

    :done
    return-void
.end method

.method public final ooscameraRestoreFilmOptions()V
    .locals 2
    sget-object v0, Lr6/g;->o:Lp6/a;
    const-string v1, "off"
    invoke-virtual {p0, v0, v1}, Lcom/oplus/camera/data/DataManager;->a(Lp6/a;Ljava/lang/Object;)Ljava/lang/Object;
    move-result-object v1
    invoke-direct {p0, v0, v1}, Lcom/oplus/camera/data/DataManager;->ooscameraGuardFilmOptions(Lp6/a;Ljava/lang/Object;)V
    return-void
.end method
