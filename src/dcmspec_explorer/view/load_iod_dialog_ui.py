# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'load_iod_dialog.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QDialog, QGridLayout, QLabel,
    QLayout, QProgressBar, QSizePolicy, QWidget)

class Ui_LoadIODDialog(object):
    def setupUi(self, LoadIODDialog):
        if not LoadIODDialog.objectName():
            LoadIODDialog.setObjectName(u"LoadIODDialog")
        LoadIODDialog.resize(400, 200)
        LoadIODDialog.setModal(True)
        self.gridLayout_2 = QGridLayout(LoadIODDialog)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.gridLayout = QGridLayout()
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
        self.label = QLabel(LoadIODDialog)
        self.label.setObjectName(u"label")

        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)

        self.label_3 = QLabel(LoadIODDialog)
        self.label_3.setObjectName(u"label_3")

        self.gridLayout.addWidget(self.label_3, 2, 0, 1, 1)

        self.label_2 = QLabel(LoadIODDialog)
        self.label_2.setObjectName(u"label_2")

        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)

        self.progressBarParseModules = QProgressBar(LoadIODDialog)
        self.progressBarParseModules.setObjectName(u"progressBarParseModules")
        self.progressBarParseModules.setValue(0)

        self.gridLayout.addWidget(self.progressBarParseModules, 2, 1, 1, 1)

        self.progressBarParseTable = QProgressBar(LoadIODDialog)
        self.progressBarParseTable.setObjectName(u"progressBarParseTable")
        self.progressBarParseTable.setValue(0)

        self.gridLayout.addWidget(self.progressBarParseTable, 1, 1, 1, 1)

        self.progressBarDownload = QProgressBar(LoadIODDialog)
        self.progressBarDownload.setObjectName(u"progressBarDownload")
        self.progressBarDownload.setValue(0)

        self.gridLayout.addWidget(self.progressBarDownload, 0, 1, 1, 1)

        self.label_4 = QLabel(LoadIODDialog)
        self.label_4.setObjectName(u"label_4")

        self.gridLayout.addWidget(self.label_4, 3, 0, 1, 1)

        self.progressBarSaveModel = QProgressBar(LoadIODDialog)
        self.progressBarSaveModel.setObjectName(u"progressBarSaveModel")
        self.progressBarSaveModel.setValue(0)

        self.gridLayout.addWidget(self.progressBarSaveModel, 3, 1, 1, 1)

        self.gridLayout.setColumnStretch(1, 1)

        self.gridLayout_2.addLayout(self.gridLayout, 0, 0, 1, 1)


        self.retranslateUi(LoadIODDialog)

        QMetaObject.connectSlotsByName(LoadIODDialog)
    # setupUi

    def retranslateUi(self, LoadIODDialog):
        LoadIODDialog.setWindowTitle(QCoreApplication.translate("LoadIODDialog", u"Loading IOD", None))
        self.label.setText(QCoreApplication.translate("LoadIODDialog", u"Downloading PS3.3", None))
        self.label_3.setText(QCoreApplication.translate("LoadIODDialog", u"Parsing IOD Modules tables", None))
        self.label_2.setText(QCoreApplication.translate("LoadIODDialog", u"Parsing IOD table", None))
        self.label_4.setText(QCoreApplication.translate("LoadIODDialog", u"Saving model", None))
    # retranslateUi

