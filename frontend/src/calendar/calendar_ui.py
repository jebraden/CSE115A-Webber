# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'calendar_ui.ui'
##
## Created by: Qt User Interface Compiler version 6.12.0
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
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout,
    QWidget)

class Ui_Calendar(object):
    def setupUi(self, Calendar):
        if not Calendar.objectName():
            Calendar.setObjectName(u"Calendar")
        Calendar.resize(1257, 750)
        self.verticalLayout_2 = QVBoxLayout(Calendar)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.label = QLabel(Calendar)
        self.label.setObjectName(u"label")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)

        self.horizontalLayout.addWidget(self.label)

        self.search_box = QLineEdit(Calendar)
        self.search_box.setObjectName(u"search_box")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.search_box.sizePolicy().hasHeightForWidth())
        self.search_box.setSizePolicy(sizePolicy1)

        self.horizontalLayout.addWidget(self.search_box)

        self.pushButton = QPushButton(Calendar)
        self.pushButton.setObjectName(u"pushButton")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.pushButton.sizePolicy().hasHeightForWidth())
        self.pushButton.setSizePolicy(sizePolicy2)

        self.horizontalLayout.addWidget(self.pushButton)


        self.verticalLayout_2.addLayout(self.horizontalLayout)

        self.stacked = QStackedWidget(Calendar)
        self.stacked.setObjectName(u"stacked")
        self.results_page = QWidget()
        self.results_page.setObjectName(u"results_page")
        self.verticalLayout = QVBoxLayout(self.results_page)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.label_2 = QLabel(self.results_page)
        self.label_2.setObjectName(u"label_2")
        sizePolicy2.setHeightForWidth(self.label_2.sizePolicy().hasHeightForWidth())
        self.label_2.setSizePolicy(sizePolicy2)

        self.horizontalLayout_2.addWidget(self.label_2, 0, Qt.AlignmentFlag.AlignRight)

        self.year_spin = QSpinBox(self.results_page)
        self.year_spin.setObjectName(u"year_spin")
        sizePolicy2.setHeightForWidth(self.year_spin.sizePolicy().hasHeightForWidth())
        self.year_spin.setSizePolicy(sizePolicy2)
        self.year_spin.setMinimum(1)
        self.year_spin.setMaximum(9999)

        self.horizontalLayout_2.addWidget(self.year_spin, 0, Qt.AlignmentFlag.AlignLeft)


        self.verticalLayout.addLayout(self.horizontalLayout_2)

        self.calendar_layout = QGridLayout()
        self.calendar_layout.setObjectName(u"calendar_layout")

        self.verticalLayout.addLayout(self.calendar_layout)

        self.stacked.addWidget(self.results_page)
        self.no_search_page = QWidget()
        self.no_search_page.setObjectName(u"no_search_page")
        self.verticalLayout_3 = QVBoxLayout(self.no_search_page)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.label_3 = QLabel(self.no_search_page)
        self.label_3.setObjectName(u"label_3")
        font = QFont()
        font.setPointSize(36)
        self.label_3.setFont(font)
        self.label_3.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout_3.addWidget(self.label_3)

        self.stacked.addWidget(self.no_search_page)
        self.no_results_page = QWidget()
        self.no_results_page.setObjectName(u"no_results_page")
        self.verticalLayout_4 = QVBoxLayout(self.no_results_page)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.label_4 = QLabel(self.no_results_page)
        self.label_4.setObjectName(u"label_4")
        self.label_4.setFont(font)
        self.label_4.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout_4.addWidget(self.label_4)

        self.stacked.addWidget(self.no_results_page)
        self.error_page = QWidget()
        self.error_page.setObjectName(u"error_page")
        self.verticalLayout_5 = QVBoxLayout(self.error_page)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.error_label = QLabel(self.error_page)
        self.error_label.setObjectName(u"error_label")
        font1 = QFont()
        font1.setPointSize(20)
        self.error_label.setFont(font1)
        self.error_label.setStyleSheet(u"QLabel {\n"
"	color: rgb(255, 0, 0);\n"
"}")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout_5.addWidget(self.error_label)

        self.error_content = QPlainTextEdit(self.error_page)
        self.error_content.setObjectName(u"error_content")
        self.error_content.setFrameShape(QFrame.Shape.NoFrame)
        self.error_content.setFrameShadow(QFrame.Shadow.Plain)
        self.error_content.setUndoRedoEnabled(False)
        self.error_content.setReadOnly(True)

        self.verticalLayout_5.addWidget(self.error_content)

        self.stacked.addWidget(self.error_page)

        self.verticalLayout_2.addWidget(self.stacked)


        self.retranslateUi(Calendar)

        self.stacked.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(Calendar)
    # setupUi

    def retranslateUi(self, Calendar):
        Calendar.setWindowTitle(QCoreApplication.translate("Calendar", u"Form", None))
        self.label.setText(QCoreApplication.translate("Calendar", u"Search:", None))
        self.pushButton.setText(QCoreApplication.translate("Calendar", u"Search", None))
        self.label_2.setText(QCoreApplication.translate("Calendar", u"Year:", None))
        self.label_3.setText(QCoreApplication.translate("Calendar", u"Use the field above to search.", None))
        self.label_4.setText(QCoreApplication.translate("Calendar", u"No snapshots matched your search.", None))
        self.error_label.setText(QCoreApplication.translate("Calendar", u"An Error Occured while performing the search!", None))
    # retranslateUi

