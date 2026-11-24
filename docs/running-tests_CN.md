# 运行测试

查看检查列表：

```bash
python3 -m gputest.cli list
```

运行级别、预览命令或使用样例数据：

```bash
python3 -m gputest.cli run --sku gb300 --level basic
python3 -m gputest.cli run --sku gb300 --level standard --dry-run
python3 -m gputest.cli run --sku a10 --level basic --mock
```

使用 `--tests name1,name2` 指定检查；多机检查使用 `--nodes host1,host2`，SSH 可使用 `--user USER` 或 `user@host`，也可使用 `--hostfile FILE`。部分 GPU 主机可使用 `--gpu-count`，`--network-mode` 可覆盖 IMDS 自动探测。

每次运行会在 `results/` 下保存 JSON/Markdown 摘要和命令原始输出。已有结果可使用 `report` 重新生成报告。基线、NCCL 启动参数和故障排查见 `doc/advanced-guide_CN.md`。
