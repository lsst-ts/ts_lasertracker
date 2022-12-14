# This file is part of ts_lasertracker.
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

import enum


class T2SAErrorCode(enum.IntEnum):
    """Error codes returned by T2SA.

    This is from a spreadsheet supplied by the vendor.
    """

    CommandRejected = 200
    CommandRejectedBusy = 201
    NoError = 300
    FailedToSetLaserOnOff = 301
    FailedToSetRandomizePoints = 302
    TwoFaceCheckFailedToleranceChecks = 303
    DriftCheckFailedToleranceChecks = 304
    MeasurememtOfPointFailed = 305
    DidFindOrSetPointGroupAndTargetName = 306
    RequestedMeasurementProfileDoesNotExist = 307
    SAReportTemplateNotFound = 308
    TwoFaceToleranceValueOutsideBoundsToleranceSetToDefault = 309
    DriftToleranceOutsideBoundsDefaultSet = 310
    LeastSquaresToleranceOutsideBounds = 311
    SATemplateFileNotFound = 312
    RefGroupNotFoundInTemplateFile = 313
    WorkingFrameNotFound = 314
    NewStationNotAddedOrCouldNotConnect = 315
    SaveSAJobFileFailed = 316
    SettingLockFailed = 317
    ResetT2SAFailed = 318
    CommandToHaltT2SAFailed = 319
    SettingT2SAToTelescopeCurrentPositionFailed = 320
    FailedSetNumberOfTimePointsAreSampled = 321
    CouldNotSetNumberOfMeasurementPointIterations = 322
    CouldNotStartInstrumentInterface = 323
    ChangeFaceFailed = 324
    FailToCreateMeasuredFrame = 325
    FailLeastSquaresBestFit = 326
    FailedToLocateInstrumentToRefPtGrp = 327
    LevelCompensatorNotSet = 328
    AddNewStationFailed = 329
    CommandToHaltT2SASucceeded = 330
    FailedToLockStation = 331
    FailedToIncMeasIndex = 332
    FailedToSetMeasIndex = 333
    ApplyT2SAToTelescopeCurrentPositionFailed = 334
    LoadTrackerCompensationFailed = 335
    FailedToSetMeasInc = 336
    FailedToSetSim = 337
    InstrumentNotReady = 338
    ClearInstrumentErrorFailed = 339
    FailedPointGroupMeasurement = 340
    NotConnectedToSA = 341
    AutoLockNotSet = 342
    HoldPositionNoBeamLockNotSet = 343
    SettingFileNotValid = 344
    SettingT2SAToTelescopeDomeCurrentPositionFailed = 345
    ObjectNotFoundInSAJob = 346
    InstrumentIdxNotValid = 347
