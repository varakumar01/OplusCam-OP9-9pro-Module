.class public final Lcom/oplus/camera/data/OosCameraFilmNotice;
.super Ljava/lang/Object;
.implements Ljava/lang/Runnable;

.method public constructor <init>()V
    .locals 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method

.method public final run()V
    .locals 3
    sget-object v0, Lcom/oplus/camera/MyApplication;->g:Lcom/oplus/camera/MyApplication;
    if-eqz v0, :done
    const-string v1, "LOG and stabilization cannot be used together on this ROM"
    const/4 v2, 0x0
    invoke-static {v0, v1, v2}, Landroid/widget/Toast;->makeText(Landroid/content/Context;Ljava/lang/CharSequence;I)Landroid/widget/Toast;
    move-result-object v1
    invoke-virtual {v1}, Landroid/widget/Toast;->show()V
    :done
    return-void
.end method
