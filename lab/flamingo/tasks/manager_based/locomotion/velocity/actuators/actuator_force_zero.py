import torch
from collections.abc import Sequence
from omni.isaac.lab.utils.assets import read_file

from omni.isaac.core.utils.types import ArticulationActions
from omni.isaac.lab.actuators import IdealPDActuator as BaseIdealPDActuator


class ForceZeroActuator(BaseIdealPDActuator):
    """Extended IdealPDActuator model with force zeroing actions functionality."""

    def __init__(self, cfg, *args, **kwargs):

        from .actuator_cfg import ForceZeroActuatorCfg

        self.cfg: ForceZeroActuatorCfg = cfg
        super().__init__(cfg, *args, **kwargs)

    def compute(
        self, control_action: ArticulationActions, joint_pos: torch.Tensor, joint_vel: torch.Tensor
    ) -> ArticulationActions:
        # compute errors
        error_pos = 0.0 - joint_pos
        error_vel = 0.0 - joint_vel
        # calculate the desired joint torques
        self.computed_effort = self.stiffness * error_pos + self.damping * error_vel + control_action.joint_efforts
        # Clip the torques based on the motor limits
        self.applied_effort = self._clip_effort(self.computed_effort)

        # Set the computed actions back into the control action
        control_action.joint_efforts = self.applied_effort
        control_action.joint_positions = None
        control_action.joint_velocities = None

        return control_action

    def reset(self, env_ids: Sequence[int]):
        # Extend reset functionality if necessary
        pass
