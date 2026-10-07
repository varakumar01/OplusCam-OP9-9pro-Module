.method public final ooscameraRefreshFilmOptions()V
    .locals 7
    iget-object v0, p0, Lyh/c;->j:Lfb/a;
    iget-object v1, p0, Lyh/c;->i:Ljb/d;
    if-eqz v0, :done
    if-eqz v1, :done
    const/4 v2, 0x0

    :loop
    invoke-virtual {v0}, Lfb/a;->getCount()I
    move-result v3
    if-ge v2, v3, :done
    invoke-virtual {v1}, Landroid/view/ViewGroup;->getChildCount()I
    move-result v3
    if-ge v2, v3, :done
    invoke-virtual {v0, v2}, Lfb/a;->j(I)Leb/a;
    move-result-object v3
    iget v4, v3, Leb/a;->d:I
    sget v5, Ljb/d;->d:I
    if-ne v4, v5, :check_eis
    sget-object v4, Lr6/g;->o:Lp6/a;
    const-string v5, "off"
    goto :read

    :check_eis
    sget v5, Ljb/d;->e:I
    if-ne v4, v5, :next
    sget-object v4, Lr6/g;->k:Lp6/a;
    const-string v5, "on"

    :read
    invoke-static {}, Lcom/oplus/camera/data/DataManager;->getInstance()Lcom/oplus/camera/data/DataManager;
    move-result-object v6
    invoke-virtual {v6, v4, v5}, Lcom/oplus/camera/data/DataManager;->a(Lp6/a;Ljava/lang/Object;)Ljava/lang/Object;
    move-result-object v5
    const-string v6, "on"
    invoke-virtual {v6, v5}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v5
    iput-boolean v5, v3, Leb/a;->e:Z
    invoke-virtual {v1, v2}, Landroid/view/ViewGroup;->getChildAt(I)Landroid/view/View;
    move-result-object v4
    const/4 v6, 0x0
    invoke-virtual {v0, v4, v2, v3, v6}, Lfb/a;->i(Landroid/view/View;ILeb/a;Z)V

    :next
    add-int/lit8 v2, v2, 0x1
    goto :loop
    :done
    return-void
.end method
