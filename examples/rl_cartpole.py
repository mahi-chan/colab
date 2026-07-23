"""Example RL training script — pass its CONTENTS as the `script` arg to launch_training.

    launch_training(
        script=open("examples/rl_cartpole.py").read(),
        run_name="ppo_cartpole",
        requirements="gymnasium[classic-control] stable-baselines3",
    )

`log_metric`, `save_checkpoint_file`, `THESIS_RUN_DIR` and `SEED` are injected by the
MCP at launch time — you do not import them.
"""

import os

import gymnasium as gym  # noqa: F401  (installed via requirements)
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.env_util import make_vec_env


class RewardLogger(BaseCallback):
    def _on_step(self) -> bool:
        for info in self.locals.get("infos", []):
            ep = info.get("episode")
            if ep is not None:
                log_metric(step=self.num_timesteps, reward=float(ep["r"]), length=int(ep["l"]))  # noqa: F821
        return True


env = make_vec_env("CartPole-v1", n_envs=1, seed=SEED)  # noqa: F821  (SEED injected)
model = PPO("MlpPolicy", env, seed=SEED, verbose=0)      # noqa: F821
model.learn(total_timesteps=50_000, callback=RewardLogger())

ckpt = os.path.join(THESIS_RUN_DIR, "checkpoints", "ppo_cartpole")  # noqa: F821
model.save(ckpt)
print("training complete; saved", ckpt)
