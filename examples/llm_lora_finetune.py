"""Example LLM fine-tune (LoRA) — pass its CONTENTS as the `script` argument.

On its own rented Hugging Face GPU (the machine stops when training ends):

    hf_job_launch(
        script=open("examples/llm_lora_finetune.py").read(),
        run_name="smollm-quotes",
        flavor="t4-small", timeout="1h",
        requirements="torch transformers peft datasets accelerate",
        env_json='{"BASE_MODEL": "HuggingFaceTB/SmolLM2-360M-Instruct", "MAX_STEPS": "300"}',
    )

Or on a connected runtime (Colab, Kaggle, hf_runtime_start) with launch_training and
the same arguments minus flavor/timeout. Follow it with get_run_status / plot_metrics
("loss"). The adapter is saved with save_checkpoint_file: to the Hub repo
<you>/<run_name> from a job, to the run's checkpoints/ folder on a runtime.

Settings come from environment variables (set them with env_json):
    BASE_MODEL   Hub id or local path of a causal language model
    DATASET      Hub dataset id, or a local .json/.jsonl file
    TEXT_FIELD   the column holding the training text
    MAX_STEPS, BATCH_SIZE, LEARNING_RATE, MAX_LENGTH, LORA_R

`log_metric`, `save_checkpoint_file`, `THESIS_RUN_DIR` and `SEED` are injected at launch
time — you do not import them. For chat-formatted supervised fine-tuning of larger
models, the same pattern works with TRL's SFTTrainer.
"""

import os

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainerCallback,
    TrainingArguments,
    set_seed,
)

BASE_MODEL = os.environ.get("BASE_MODEL", "HuggingFaceTB/SmolLM2-135M-Instruct")
DATASET = os.environ.get("DATASET", "Abirate/english_quotes")
TEXT_FIELD = os.environ.get("TEXT_FIELD", "quote")
MAX_STEPS = int(os.environ.get("MAX_STEPS", "200"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "8"))
LEARNING_RATE = float(os.environ.get("LEARNING_RATE", "2e-4"))
MAX_LENGTH = int(os.environ.get("MAX_LENGTH", "256"))
LORA_R = int(os.environ.get("LORA_R", "16"))

set_seed(SEED)  # noqa: F821  (injected)
cuda = torch.cuda.is_available()
print("device:", torch.cuda.get_device_name(0) if cuda else "cpu")

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
model = AutoModelForCausalLM.from_pretrained(BASE_MODEL)
model = get_peft_model(model, LoraConfig(
    r=LORA_R, lora_alpha=2 * LORA_R, lora_dropout=0.05,
    target_modules="all-linear", task_type="CAUSAL_LM",
))
model.print_trainable_parameters()

if os.path.isfile(DATASET):
    data = load_dataset("json", data_files=DATASET, split="train")
else:
    data = load_dataset(DATASET, split=os.environ.get("DATASET_SPLIT", "train"))
data = data.map(
    lambda batch: tokenizer(batch[TEXT_FIELD], truncation=True, max_length=MAX_LENGTH),
    batched=True, remove_columns=data.column_names,
)


class MetricLogger(TrainerCallback):
    """Forward the Trainer's numbers (loss, learning rate, ...) to the MCP's metrics."""

    def on_log(self, args, state, control, logs=None, **kwargs):
        numbers = {k: v for k, v in (logs or {}).items() if isinstance(v, (int, float))}
        if numbers:
            log_metric(step=state.global_step, **numbers)  # noqa: F821  (injected)


work_dir = os.path.join(THESIS_RUN_DIR, "work")  # noqa: F821  (injected)
trainer = Trainer(
    model=model,
    args=TrainingArguments(
        output_dir=work_dir,
        max_steps=MAX_STEPS,
        per_device_train_batch_size=BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        logging_steps=max(1, MAX_STEPS // 40),
        save_strategy="no",
        report_to="none",
        seed=SEED,  # noqa: F821
        bf16=cuda and torch.cuda.is_bf16_supported(),
        fp16=cuda and not torch.cuda.is_bf16_supported(),
    ),
    train_dataset=data,
    data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    callbacks=[MetricLogger()],
)
trainer.train()

adapter_dir = os.path.join(work_dir, "adapter")
model.save_pretrained(adapter_dir)
tokenizer.save_pretrained(adapter_dir)
print("adapter saved to", save_checkpoint_file(adapter_dir, "adapter"))  # noqa: F821

model.eval()
prompt = tokenizer("The", return_tensors="pt").to(model.device)
with torch.no_grad():
    sample = model.generate(**prompt, max_new_tokens=30, do_sample=False,
                            pad_token_id=tokenizer.pad_token_id)
print("sample:", tokenizer.decode(sample[0], skip_special_tokens=True))
print("training complete")
