.method public final d(Lrh/d;Lcom/oplus/camera/CameraManager$e;)V
    .locals 5

    # Caller c() retains camera-state, thumbnail and URI validity checks.
    if-eqz p1, :done
    iget-object v0, p1, Lrh/d;->b:Landroid/net/Uri;
    if-eqz v0, :done
    iget-object v1, p0, Lcom/oplus/camera/CameraManager$e;->b:Lcom/oplus/camera/CameraManager;
    iget-object v1, v1, Lcom/oplus/camera/CameraManager;->w:Landroid/app/Activity;

    # A generic gallery must be opened after unlocking the device.
    const-string v2, "keyguard"
    invoke-virtual {v1, v2}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;
    move-result-object v2
    check-cast v2, Landroid/app/KeyguardManager;
    invoke-virtual {v2}, Landroid/app/KeyguardManager;->isKeyguardLocked()Z
    move-result v2
    if-eqz v2, :unlocked
    const-string v2, "Unlock to open gallery"
    goto :toast

    :unlocked
    :try_start
    new-instance v2, Landroid/content/Intent;
    const-string v3, "android.intent.action.VIEW"
    invoke-direct {v2, v3}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V
    iget-object v3, p1, Lrh/d;->c:Ljava/lang/String;
    invoke-virtual {v2, v0, v3}, Landroid/content/Intent;->setDataAndType(Landroid/net/Uri;Ljava/lang/String;)Landroid/content/Intent;
    const/4 v3, 0x1
    invoke-virtual {v2, v3}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;
    invoke-virtual {v1, v2}, Landroid/app/Activity;->startActivity(Landroid/content/Intent;)V
    :try_end
    .catch Landroid/content/ActivityNotFoundException; {:try_start .. :try_end} :no_viewer
    goto :done

    :no_viewer
    move-exception v4
    const-string v2, "No app can open this media"
    :toast
    const/4 v3, 0x0
    invoke-static {v1, v2, v3}, Landroid/widget/Toast;->makeText(Landroid/content/Context;Ljava/lang/CharSequence;I)Landroid/widget/Toast;
    move-result-object v2
    invoke-virtual {v2}, Landroid/widget/Toast;->show()V

    :done
    return-void
.end method
