# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMenuBar,
    QPushButton, QSizePolicy, QSpacerItem, QSplitter,
    QStatusBar, QTextBrowser, QTreeView, QVBoxLayout,
    QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1400, 768)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(MainWindow.sizePolicy().hasHeightForWidth())
        MainWindow.setSizePolicy(sizePolicy)
        MainWindow.setMaximumSize(QSize(16777215, 16777215))
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout_3 = QVBoxLayout(self.centralwidget)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.controlArea = QWidget(self.centralwidget)
        self.controlArea.setObjectName(u"controlArea")
        self.controlArea.setEnabled(True)
        sizePolicy.setHeightForWidth(self.controlArea.sizePolicy().hasHeightForWidth())
        self.controlArea.setSizePolicy(sizePolicy)
        self.horizontalLayout = QHBoxLayout(self.controlArea)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.showAllPushButton = QPushButton(self.controlArea)
        self.showAllPushButton.setObjectName(u"showAllPushButton")

        self.horizontalLayout.addWidget(self.showAllPushButton)

        self.searchLineEdit = QLineEdit(self.controlArea)
        self.searchLineEdit.setObjectName(u"searchLineEdit")
        self.searchLineEdit.setEnabled(True)
        sizePolicy.setHeightForWidth(self.searchLineEdit.sizePolicy().hasHeightForWidth())
        self.searchLineEdit.setSizePolicy(sizePolicy)
        self.searchLineEdit.setClearButtonEnabled(True)

        self.horizontalLayout.addWidget(self.searchLineEdit)

        self.horizontalSpacer = QSpacerItem(700, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.versionLabel = QLabel(self.controlArea)
        self.versionLabel.setObjectName(u"versionLabel")

        self.horizontalLayout.addWidget(self.versionLabel)

        self.reloadPushButton = QPushButton(self.controlArea)
        self.reloadPushButton.setObjectName(u"reloadPushButton")

        self.horizontalLayout.addWidget(self.reloadPushButton)


        self.verticalLayout_3.addWidget(self.controlArea)

        self.splitter = QSplitter(self.centralwidget)
        self.splitter.setObjectName(u"splitter")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.splitter.sizePolicy().hasHeightForWidth())
        self.splitter.setSizePolicy(sizePolicy1)
        self.splitter.setOrientation(Qt.Orientation.Horizontal)
        self.iodlistarea = QWidget(self.splitter)
        self.iodlistarea.setObjectName(u"iodlistarea")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.iodlistarea.sizePolicy().hasHeightForWidth())
        self.iodlistarea.setSizePolicy(sizePolicy2)
        self.iodlistarea.setMinimumSize(QSize(600, 0))
        self.verticalLayout = QVBoxLayout(self.iodlistarea)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.iodLabel = QLabel(self.iodlistarea)
        self.iodLabel.setObjectName(u"iodLabel")

        self.verticalLayout.addWidget(self.iodLabel)

        self.iodTreeView = QTreeView(self.iodlistarea)
        self.iodTreeView.setObjectName(u"iodTreeView")
        self.iodTreeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.verticalLayout.addWidget(self.iodTreeView)

        self.splitter.addWidget(self.iodlistarea)
        self.detailsArea = QWidget(self.splitter)
        self.detailsArea.setObjectName(u"detailsArea")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy3.setHorizontalStretch(1)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.detailsArea.sizePolicy().hasHeightForWidth())
        self.detailsArea.setSizePolicy(sizePolicy3)
        self.verticalLayout_2 = QVBoxLayout(self.detailsArea)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.detailsLabel = QLabel(self.detailsArea)
        self.detailsLabel.setObjectName(u"detailsLabel")

        self.verticalLayout_2.addWidget(self.detailsLabel)

        self.detailsTextBrowser = QTextBrowser(self.detailsArea)
        self.detailsTextBrowser.setObjectName(u"detailsTextBrowser")
        self.detailsTextBrowser.setOpenExternalLinks(True)

        self.verticalLayout_2.addWidget(self.detailsTextBrowser)

        self.splitter.addWidget(self.detailsArea)

        self.verticalLayout_3.addWidget(self.splitter)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1400, 43))
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"DCMspec Explorer", None))
        self.showAllPushButton.setText(QCoreApplication.translate("MainWindow", u"Reload", None))
        self.searchLineEdit.setPlaceholderText(QCoreApplication.translate("MainWindow", u"Search...", None))
        self.versionLabel.setText(QCoreApplication.translate("MainWindow", u"Version", None))
        self.reloadPushButton.setText(QCoreApplication.translate("MainWindow", u"Show All", None))
        self.iodLabel.setText(QCoreApplication.translate("MainWindow", u"IOD List", None))
        self.detailsLabel.setText(QCoreApplication.translate("MainWindow", u"Details", None))
    # retranslateUi

