# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Script to play a checkpoint if an RL agent from RSL-RL."""

"""Launch Isaac Sim Simulator first."""

import argparse

from omni.isaac.lab.app import AppLauncher
import matplotlib.pyplot as plt

# local imports
import cli_args  # isort: skip

# add argparse arguments
parser = argparse.ArgumentParser(description="Train an RL agent with RSL-RL.")
parser.add_argument("--video", action="store_true", default=False, help="Record videos during training.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video (in steps).")
parser.add_argument(
    "--disable_fabric", action="store_true", default=False, help="Disable fabric and use USD I/O operations."
)
parser.add_argument("--num_envs", type=int, default=None, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default=None, help="Name of the task.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment")
# append RSL-RL cli arguments
cli_args.add_rsl_rl_args(parser)
# append AppLauncher cli args
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
# always enable cameras to record video
if args_cli.video:
    args_cli.enable_cameras = True

# launch omniverse app
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

"""Rest everything follows."""

import gymnasium as gym
import os
import torch

from rsl_rl.runners import OnPolicyRunner

from omni.isaac.lab.utils.dict import print_dict

from lab.flamingo.tasks.utils.wrappers.rsl_rl import RslRlVecEnvWrapper

# Import extensions to set up environment tasks
import lab.flamingo.tasks  # noqa: F401  TODO: import orbit.<your_extension_name>

from omni.isaac.lab_tasks.utils import get_checkpoint_path, parse_env_cfg
from omni.isaac.lab_tasks.utils.wrappers.rsl_rl import (
    RslRlOnPolicyRunnerCfg,
    export_policy_as_jit,
    export_policy_as_onnx,
)


def main():
    """Play with RSL-RL agent."""
    # parse configuration
    env_cfg = parse_env_cfg(
        args_cli.task, device=args_cli.device, num_envs=args_cli.num_envs, use_fabric=not args_cli.disable_fabric
    )
    agent_cfg: RslRlOnPolicyRunnerCfg = cli_args.parse_rsl_rl_cfg(args_cli.task, args_cli)

    # specify directory for logging experiments
    log_root_path = os.path.join("logs", "rsl_rl", agent_cfg.experiment_name)
    log_root_path = os.path.abspath(log_root_path)
    print(f"[INFO] Loading experiment from directory: {log_root_path}")
    resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)
    log_dir = os.path.dirname(resume_path)

    # create isaac environment
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)
    # wrap for video recording
    if args_cli.video:
        video_kwargs = {
            "video_folder": os.path.join(log_dir, "videos", "play"),
            "step_trigger": lambda step: step == 0,
            "video_length": args_cli.video_length,
            "disable_logger": True,
        }
        print("[INFO] Recording videos during training.")
        print_dict(video_kwargs, nesting=4)
        env = gym.wrappers.RecordVideo(env, **video_kwargs)
    # wrap around environment for rsl-rl
    env = RslRlVecEnvWrapper(env)

    print(f"[INFO]: Loading model checkpoint from: {resume_path}")
    # load previously trained model
    ppo_runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    ppo_runner.load(resume_path)

    # obtain the trained policy for inference
    policy = ppo_runner.get_inference_policy(device=env.unwrapped.device)

    # export policy to onnx/jit
    export_model_dir = os.path.join(os.path.dirname(resume_path), "exported")
    export_policy_as_jit(
        ppo_runner.alg.actor_critic, ppo_runner.obs_normalizer, path=export_model_dir, filename="policy.pt"
    )
    export_policy_as_onnx(
        ppo_runner.alg.actor_critic, normalizer=ppo_runner.obs_normalizer, path=export_model_dir, filename="policy.onnx"
    )

    # Initialize lists to store data
    joint_pos_list = []
    target_joint_pos_list = []
    joint_velocity_obs_list = []
    target_joint_velocity_list = []

    # reset environment
    obs, _ = env.get_observations()
    timestep = 0
    # Simulate environment and collect data
    while simulation_app.is_running():
        with torch.inference_mode():
            actions = policy(obs)
            obs, _, _, _ = env.step(actions)
        if args_cli.video:
            timestep += 1
            # Exit the play loop after recording one video
            if timestep == args_cli.video_length:
                break
        # Extract the relevant slices and convert to numpy
        joint_pos = obs[0, :6].cpu().numpy()
        target_joint_pos = (obs[0, 48:54] * 1.0).cpu().numpy()
        joint_velocity_obs = obs[0, 12:14].cpu().numpy()
        target_joint_velocity = (obs[0, 54:56] * 55.0).cpu().numpy()

        # Store the data
        joint_pos_list.append(joint_pos)
        target_joint_pos_list.append(target_joint_pos)
        joint_velocity_obs_list.append(joint_velocity_obs)
        target_joint_velocity_list.append(target_joint_velocity)

    env.close()

    # Plot the collected data after the simulation ends
    plt.figure(figsize=(14, 16))

    for i in range(6):
        plt.subplot(4, 2, i + 1)
        plt.plot([step[i] for step in joint_pos_list], label=f"Joint Position {i+1}")
        plt.plot([step[i] for step in target_joint_pos_list], label=f"Target Joint Position {i+1}", linestyle="--")
        plt.title(f"Joint Position {i+1} and Target Joint Position", fontsize=10, pad=10)  # Added pad for spacing
        plt.legend()

    for i in range(2):
        plt.subplot(4, 2, i + 7)
        plt.plot([step[i] for step in joint_velocity_obs_list], label=f"Observed Joint Velocity {i+1}")
        plt.plot([step[i] for step in target_joint_velocity_list], label=f"Target Joint Velocity {i+1}", linestyle="--")
        plt.title(f"Observed and Target Joint Velocity {i+1}", fontsize=10, pad=10)  # Added pad for spacing
        plt.legend()

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    # run the main function
    main()
    # close sim app
    simulation_app.close()
