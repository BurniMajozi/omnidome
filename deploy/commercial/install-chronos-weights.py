"""Operator setup: public Amazon weights only; application inference stays offline."""
from huggingface_hub import snapshot_download
snapshot_download('amazon/chronos-bolt-small',local_dir='/models/chronos-bolt-small',allow_patterns=['config.json','model.safetensors','pytorch_model.bin','generation_config.json'])
print('Amazon Chronos-Bolt small weights ready')
