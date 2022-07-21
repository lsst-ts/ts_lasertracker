# This file is part of ts_MTAlignment.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = ["T2SAErrorCode"]

from enum import IntEnum


class T2SAErrors(IntEnum):
    NoError = 200
    CommandRejected = 300
    FailedToSetLaserOff = 301
    FailedToSetRandomizePoints = 302
    TwoFaceCheckFailedTolerenceCheck = 303

    DriftCheckFailedToleranceCheck = 304
    MeasurementOfPointFailed = 305
    # DidNotFindOrSetPointGroupAndTargetName = 306
    RequestedMeasurementProfileDoesNotExist = 307
    SAReportTemplateNotFound = 308

    TwoFaceToleraneValueOutsideBoundsToleranceSetToDefault = 309
    DriftToleranceOutsideBoundsDefaultSet = 310
    LeastSquaresToleranceOutsideBounds = 311
    SATemplateNotFound = 312
    RefGroupNotFoundInTemplateFile = 313

    WorkingFrameNotFound = 314
    NewStationNotAddedOrCouldNotConnect = 315
    SaveSAJobFileFileFailed = 316
    SettingLockFailed = 317
    ResetT2SAFailed = 318

    CommandToHaltT2SAFailed = 319
    SettingT2SAToTelescopeCurrentPositionFailed = 320
    FaildSetNumberOfTimesPointsAreSampled = 321
    CouldNotSetNumberOfMeasurementsPointIterations = 322
    COuldNotStartInstrumentInterface = 323

    ChangeFaceFailed = 324
    FailToCreateMeasuredFrame = 325
    FailLeastSquareBestFit = 326
    FailedTOLocateInstrumentToRefPointGroup = 327
    LevelCompensatorNotSet = 328

    AddNewStationFailed = 329
    CommandToHaltT2SASucceeded = 330
    FailedToLockStation = 331
    FailedToIncMeasIndex = 332
