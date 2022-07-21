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
