import wpilib
from wpilib import controller
import ctre
from numpy import interp
from magicbot import feedback, tunable


class Shooter:
    outer_motor: ctre.WPI_TalonFX
    centre_motor: ctre.WPI_TalonFX
    loading_piston: wpilib.Solenoid

    ranges = (0, 7, 8, 9, 10, 11)  # TODO remove 0 and add more data points
    centre_rpms = (0, 880, 1120, 1500, 2150, 2400)
    outer_rpms = (5000, 5000, 5000, 5000, 5000, 5000)

    outer_target = tunable(0)
    centre_target = tunable(0)

    COUNTS_PER_REV = 2048
    RPS_TO_CTRE_UNITS = COUNTS_PER_REV / 10  # counts per 100ms
    CTRE_UNITS_TO_RPS = 1 / RPS_TO_CTRE_UNITS

    def __init__(self):
        self.inject = False
        self.in_range = False
        self.velocity_tolerance = 0.05  # of setpoint

    def on_enable(self) -> None:
        self.centre_motor.stopMotor()
        self.outer_motor.stopMotor()

    def setup(self) -> None:
        self.loading_piston.setPulseDuration(0.5)

        self.outer_motor.setInverted(True)
        self.centre_motor.setInverted(False)

        self.outer_motor.setNeutralMode(ctre.NeutralMode.Coast)
        self.centre_motor.setNeutralMode(ctre.NeutralMode.Coast)

        self.outer_motor.config_kP(0, 0.00394 * self.RPS_TO_CTRE_UNITS / 10)
        self.outer_motor.config_kI(0, 0)
        self.outer_motor.config_kD(0, 0)
        self.outer_motor.config_kF(0, 0)
        self.outer_ff_calculator = controller.SimpleMotorFeedforward(kS=0.187, kV=0.11)
        self.centre_motor.config_kP(0, 0.0042 * self.RPS_TO_CTRE_UNITS / 10)
        self.centre_motor.config_kI(0, 0)
        self.centre_motor.config_kD(0, 0)
        self.centre_motor.config_kF(0, 0)
        self.centre_ff_calculator = controller.SimpleMotorFeedforward(kS=0.158, kV=0.11)

    def execute(self) -> None:
        voltage = wpilib.RobotController.getInputVoltage()
        centre_feed_forward = (
            self.centre_ff_calculator.calculate(self.centre_target) / voltage
        )
        outer_feed_forward = (
            self.outer_ff_calculator.calculate(self.outer_target) / voltage
        )
        self.centre_motor.set(
            ctre.ControlMode.Velocity,
            self.centre_target * self.RPS_TO_CTRE_UNITS,
            ctre.DemandType.ArbitraryFeedForward,
            centre_feed_forward,
        )
        self.outer_motor.set(
            ctre.ControlMode.Velocity,
            self.outer_target * self.RPS_TO_CTRE_UNITS,
            ctre.DemandType.ArbitraryFeedForward,
            outer_feed_forward,
        )

        if self.inject:
            self.loading_piston.startPulse()
            self.inject = False

    def set_range(self, dist: float) -> None:
        """
        Set the target range for the shooter, this will be converted into target speeds for the flywheels
        dist: planar distance from the power port
        """
        if self.ranges[0] <= dist <= self.ranges[-1]:
            self.in_range = True
        else:
            # clamp the range between our minimum and maximum
            dist = min(self.ranges[-1], max(dist, self.ranges[0]))
            self.in_range = False
        self.centre_target = interp(dist, self.ranges, self.centre_rpms)
        self.outer_target = interp(dist, self.ranges, self.outer_rpms)

    @feedback
    def is_at_speed(self) -> bool:
        """
        Returns true if the shooter is spinning at the set speed.

        Considers the rotation rates of the flywheels compared with their setpoints
        """
        return (
            abs(self.centre_target - self.get_centre_velocity())
            <= self.centre_target * self.velocity_tolerance
            and abs(self.outer_target - self.get_outer_velocity())
            <= self.outer_target * self.velocity_tolerance
        )

    @feedback
    def get_centre_velocity(self):
        """Returns velocity in rps"""
        return self.centre_motor.getSelectedSensorVelocity() * self.CTRE_UNITS_TO_RPS

    @feedback
    def get_outer_velocity(self):
        """Returns velocity in rps"""
        return self.outer_motor.getSelectedSensorVelocity() * self.CTRE_UNITS_TO_RPS

    @feedback
    def is_firing(self) -> bool:
        """
        Returns true if the shooter is attempting a shot.

        based off of the pistons current state
        """
        return self.loading_piston.get()

    @feedback
    def is_in_range(self) -> bool:
        """
        Returns true if the current target of the shooter is within range
        Returns false if the range has been clamped
        """
        return self.in_range

    @feedback
    def is_ready(self) -> bool:
        """
        Returns true if the shooter is ready to take a shot.

        Checks the speed, range and whether the piston is moving
        """
        # print(f"in range {self.is_in_range()} at speed {self.is_at_speed()} is firing {self.is_firing()}")
        return self.is_in_range() and self.is_at_speed() and not self.is_firing()

    def fire(self) -> None:
        """
        Inject a ball into the shooter
        """
        self.inject = True
