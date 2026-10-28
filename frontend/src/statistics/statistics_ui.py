# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'statistics_ui.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QAbstractScrollArea, QApplication, QButtonGroup,
    QCheckBox, QDateTimeEdit, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QPlainTextEdit, QPushButton, QRadioButton, QSizePolicy,
    QSpacerItem, QSpinBox, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

class Ui_StatisticsWidget(object):
    def setupUi(self, StatisticsWidget):
        if not StatisticsWidget.objectName():
            StatisticsWidget.setObjectName(u"StatisticsWidget")
        StatisticsWidget.resize(1191, 799)
        self.verticalLayout_2 = QVBoxLayout(StatisticsWidget)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.range_box = QGroupBox(StatisticsWidget)
        self.range_box.setObjectName(u"range_box")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.range_box.sizePolicy().hasHeightForWidth())
        self.range_box.setSizePolicy(sizePolicy)
        self.gridLayout = QGridLayout(self.range_box)
        self.gridLayout.setObjectName(u"gridLayout")
        self.custom_period_box = QWidget(self.range_box)
        self.custom_period_box.setObjectName(u"custom_period_box")
        self.custom_period_box.setEnabled(False)
        self.horizontalLayout_2 = QHBoxLayout(self.custom_period_box)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.custom_start_label = QLabel(self.custom_period_box)
        self.custom_start_label.setObjectName(u"custom_start_label")

        self.horizontalLayout_2.addWidget(self.custom_start_label)

        self.verticalLayout_3 = QVBoxLayout()
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.custom_start = QDateTimeEdit(self.custom_period_box)
        self.custom_start.setObjectName(u"custom_start")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.custom_start.sizePolicy().hasHeightForWidth())
        self.custom_start.setSizePolicy(sizePolicy1)
        self.custom_start.setTimeSpec(Qt.TimeSpec.UTC)

        self.verticalLayout_3.addWidget(self.custom_start)

        self.custom_start_check = QCheckBox(self.custom_period_box)
        self.custom_start_check.setObjectName(u"custom_start_check")

        self.verticalLayout_3.addWidget(self.custom_start_check)


        self.horizontalLayout_2.addLayout(self.verticalLayout_3)

        self.horizontalSpacer_2 = QSpacerItem(20, 17, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer_2)

        self.custom_end_label = QLabel(self.custom_period_box)
        self.custom_end_label.setObjectName(u"custom_end_label")

        self.horizontalLayout_2.addWidget(self.custom_end_label)

        self.verticalLayout_4 = QVBoxLayout()
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.custom_end = QDateTimeEdit(self.custom_period_box)
        self.custom_end.setObjectName(u"custom_end")
        sizePolicy1.setHeightForWidth(self.custom_end.sizePolicy().hasHeightForWidth())
        self.custom_end.setSizePolicy(sizePolicy1)
        self.custom_end.setTimeSpec(Qt.TimeSpec.UTC)

        self.verticalLayout_4.addWidget(self.custom_end)

        self.custom_end_check = QCheckBox(self.custom_period_box)
        self.custom_end_check.setObjectName(u"custom_end_check")

        self.verticalLayout_4.addWidget(self.custom_end_check)


        self.horizontalLayout_2.addLayout(self.verticalLayout_4)

        self.horizontalSpacer = QSpacerItem(20, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer)

        self.data_points_label = QLabel(self.custom_period_box)
        self.data_points_label.setObjectName(u"data_points_label")

        self.horizontalLayout_2.addWidget(self.data_points_label)

        self.data_points_spin = QSpinBox(self.custom_period_box)
        self.data_points_spin.setObjectName(u"data_points_spin")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.data_points_spin.sizePolicy().hasHeightForWidth())
        self.data_points_spin.setSizePolicy(sizePolicy2)
        self.data_points_spin.setMinimum(1)
        self.data_points_spin.setMaximum(2147483647)

        self.horizontalLayout_2.addWidget(self.data_points_spin)


        self.gridLayout.addWidget(self.custom_period_box, 1, 1, 1, 5)

        self.month_radio = QRadioButton(self.range_box)
        self.period_buttons = QButtonGroup(StatisticsWidget)
        self.period_buttons.setObjectName(u"period_buttons")
        self.period_buttons.addButton(self.month_radio)
        self.month_radio.setObjectName(u"month_radio")

        self.gridLayout.addWidget(self.month_radio, 0, 3, 1, 1)

        self.year_radio = QRadioButton(self.range_box)
        self.period_buttons.addButton(self.year_radio)
        self.year_radio.setObjectName(u"year_radio")

        self.gridLayout.addWidget(self.year_radio, 0, 4, 1, 1)

        self.generate_button = QPushButton(self.range_box)
        self.generate_button.setObjectName(u"generate_button")
        self.generate_button.setEnabled(True)
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.generate_button.sizePolicy().hasHeightForWidth())
        self.generate_button.setSizePolicy(sizePolicy3)
        self.generate_button.setCheckable(False)
        self.generate_button.setFlat(False)

        self.gridLayout.addWidget(self.generate_button, 1, 6, 1, 1, Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter)

        self.all_time_radio = QRadioButton(self.range_box)
        self.period_buttons.addButton(self.all_time_radio)
        self.all_time_radio.setObjectName(u"all_time_radio")

        self.gridLayout.addWidget(self.all_time_radio, 0, 5, 1, 1)

        self.yesterday_radio = QRadioButton(self.range_box)
        self.period_buttons.addButton(self.yesterday_radio)
        self.yesterday_radio.setObjectName(u"yesterday_radio")

        self.gridLayout.addWidget(self.yesterday_radio, 0, 1, 1, 1)

        self.today_radio = QRadioButton(self.range_box)
        self.period_buttons.addButton(self.today_radio)
        self.today_radio.setObjectName(u"today_radio")
        self.today_radio.setChecked(True)

        self.gridLayout.addWidget(self.today_radio, 0, 0, 1, 1)

        self.custom_radio = QRadioButton(self.range_box)
        self.period_buttons.addButton(self.custom_radio)
        self.custom_radio.setObjectName(u"custom_radio")

        self.gridLayout.addWidget(self.custom_radio, 1, 0, 1, 1)

        self.week_radio = QRadioButton(self.range_box)
        self.period_buttons.addButton(self.week_radio)
        self.week_radio.setObjectName(u"week_radio")

        self.gridLayout.addWidget(self.week_radio, 0, 2, 1, 1)


        self.verticalLayout_2.addWidget(self.range_box)

        self.stacked_content = QStackedWidget(StatisticsWidget)
        self.stacked_content.setObjectName(u"stacked_content")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.stacked_content.sizePolicy().hasHeightForWidth())
        self.stacked_content.setSizePolicy(sizePolicy4)
        self.request_page = QWidget()
        self.request_page.setObjectName(u"request_page")
        sizePolicy4.setHeightForWidth(self.request_page.sizePolicy().hasHeightForWidth())
        self.request_page.setSizePolicy(sizePolicy4)
        self.verticalLayout_5 = QVBoxLayout(self.request_page)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_5.addItem(self.verticalSpacer)

        self.label = QLabel(self.request_page)
        self.label.setObjectName(u"label")
        sizePolicy3.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy3)
        font = QFont()
        font.setPointSize(28)
        self.label.setFont(font)
        self.label.setAlignment(Qt.AlignmentFlag.AlignBottom|Qt.AlignmentFlag.AlignHCenter)

        self.verticalLayout_5.addWidget(self.label)

        self.label_2 = QLabel(self.request_page)
        self.label_2.setObjectName(u"label_2")
        sizePolicy3.setHeightForWidth(self.label_2.sizePolicy().hasHeightForWidth())
        self.label_2.setSizePolicy(sizePolicy3)
        font1 = QFont()
        font1.setPointSize(15)
        self.label_2.setFont(font1)
        self.label_2.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout_5.addWidget(self.label_2)

        self.cancel_button = QPushButton(self.request_page)
        self.cancel_button.setObjectName(u"cancel_button")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.cancel_button.sizePolicy().hasHeightForWidth())
        self.cancel_button.setSizePolicy(sizePolicy5)

        self.verticalLayout_5.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignHCenter)

        self.verticalSpacer_2 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_5.addItem(self.verticalSpacer_2)

        self.stacked_content.addWidget(self.request_page)
        self.stats_page = QWidget()
        self.stats_page.setObjectName(u"stats_page")
        self.horizontalLayout_3 = QHBoxLayout(self.stats_page)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.splitter = QSplitter(self.stats_page)
        self.splitter.setObjectName(u"splitter")
        self.splitter.setOrientation(Qt.Orientation.Horizontal)
        self.graph_box = QGroupBox(self.splitter)
        self.graph_box.setObjectName(u"graph_box")
        sizePolicy4.setHeightForWidth(self.graph_box.sizePolicy().hasHeightForWidth())
        self.graph_box.setSizePolicy(sizePolicy4)
        self.verticalLayout = QVBoxLayout(self.graph_box)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.graph_button_layout = QHBoxLayout()
        self.graph_button_layout.setObjectName(u"graph_button_layout")
        self.snapshots_graph_radio = QRadioButton(self.graph_box)
        self.graph_buttons = QButtonGroup(StatisticsWidget)
        self.graph_buttons.setObjectName(u"graph_buttons")
        self.graph_buttons.addButton(self.snapshots_graph_radio)
        self.snapshots_graph_radio.setObjectName(u"snapshots_graph_radio")
        self.snapshots_graph_radio.setChecked(True)

        self.graph_button_layout.addWidget(self.snapshots_graph_radio)

        self.files_graph_radio = QRadioButton(self.graph_box)
        self.graph_buttons.addButton(self.files_graph_radio)
        self.files_graph_radio.setObjectName(u"files_graph_radio")

        self.graph_button_layout.addWidget(self.files_graph_radio)

        self.size_graph_radio = QRadioButton(self.graph_box)
        self.graph_buttons.addButton(self.size_graph_radio)
        self.size_graph_radio.setObjectName(u"size_graph_radio")

        self.graph_button_layout.addWidget(self.size_graph_radio)

        self.urls_graph_radio = QRadioButton(self.graph_box)
        self.graph_buttons.addButton(self.urls_graph_radio)
        self.urls_graph_radio.setObjectName(u"urls_graph_radio")

        self.graph_button_layout.addWidget(self.urls_graph_radio)

        self.hosts_graph_radio = QRadioButton(self.graph_box)
        self.graph_buttons.addButton(self.hosts_graph_radio)
        self.hosts_graph_radio.setObjectName(u"hosts_graph_radio")

        self.graph_button_layout.addWidget(self.hosts_graph_radio)


        self.verticalLayout.addLayout(self.graph_button_layout)

        self.graph_wrapper = QWidget(self.graph_box)
        self.graph_wrapper.setObjectName(u"graph_wrapper")
        sizePolicy4.setHeightForWidth(self.graph_wrapper.sizePolicy().hasHeightForWidth())
        self.graph_wrapper.setSizePolicy(sizePolicy4)

        self.verticalLayout.addWidget(self.graph_wrapper)

        self.horizontalLayout_5 = QHBoxLayout()
        self.horizontalLayout_5.setSpacing(0)
        self.horizontalLayout_5.setObjectName(u"horizontalLayout_5")
        self.dx_label_label = QLabel(self.graph_box)
        self.dx_label_label.setObjectName(u"dx_label_label")
        sizePolicy6 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        sizePolicy6.setHorizontalStretch(0)
        sizePolicy6.setVerticalStretch(0)
        sizePolicy6.setHeightForWidth(self.dx_label_label.sizePolicy().hasHeightForWidth())
        self.dx_label_label.setSizePolicy(sizePolicy6)

        self.horizontalLayout_5.addWidget(self.dx_label_label)

        self.dx_label = QLabel(self.graph_box)
        self.dx_label.setObjectName(u"dx_label")
        sizePolicy7 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy7.setHorizontalStretch(0)
        sizePolicy7.setVerticalStretch(0)
        sizePolicy7.setHeightForWidth(self.dx_label.sizePolicy().hasHeightForWidth())
        self.dx_label.setSizePolicy(sizePolicy7)

        self.horizontalLayout_5.addWidget(self.dx_label)


        self.verticalLayout.addLayout(self.horizontalLayout_5)

        self.splitter.addWidget(self.graph_box)
        self.numbers_box = QGroupBox(self.splitter)
        self.numbers_box.setObjectName(u"numbers_box")
        self.numbers_box.setFlat(False)
        self.numbers_box.setCheckable(False)
        self.horizontalLayout_4 = QHBoxLayout(self.numbers_box)
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.stats_table = QTableWidget(self.numbers_box)
        if (self.stats_table.columnCount() < 1):
            self.stats_table.setColumnCount(1)
        __qtablewidgetitem = QTableWidgetItem()
        self.stats_table.setHorizontalHeaderItem(0, __qtablewidgetitem)
        if (self.stats_table.rowCount() < 6):
            self.stats_table.setRowCount(6)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.stats_table.setVerticalHeaderItem(0, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.stats_table.setVerticalHeaderItem(1, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.stats_table.setVerticalHeaderItem(2, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.stats_table.setVerticalHeaderItem(3, __qtablewidgetitem4)
        __qtablewidgetitem5 = QTableWidgetItem()
        self.stats_table.setVerticalHeaderItem(4, __qtablewidgetitem5)
        __qtablewidgetitem6 = QTableWidgetItem()
        self.stats_table.setVerticalHeaderItem(5, __qtablewidgetitem6)
        __qtablewidgetitem7 = QTableWidgetItem()
        self.stats_table.setItem(0, 0, __qtablewidgetitem7)
        __qtablewidgetitem8 = QTableWidgetItem()
        self.stats_table.setItem(1, 0, __qtablewidgetitem8)
        __qtablewidgetitem9 = QTableWidgetItem()
        self.stats_table.setItem(2, 0, __qtablewidgetitem9)
        __qtablewidgetitem10 = QTableWidgetItem()
        self.stats_table.setItem(3, 0, __qtablewidgetitem10)
        __qtablewidgetitem11 = QTableWidgetItem()
        self.stats_table.setItem(4, 0, __qtablewidgetitem11)
        __qtablewidgetitem12 = QTableWidgetItem()
        self.stats_table.setItem(5, 0, __qtablewidgetitem12)
        self.stats_table.setObjectName(u"stats_table")
        sizePolicy8 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        sizePolicy8.setHorizontalStretch(0)
        sizePolicy8.setVerticalStretch(0)
        sizePolicy8.setHeightForWidth(self.stats_table.sizePolicy().hasHeightForWidth())
        self.stats_table.setSizePolicy(sizePolicy8)
        self.stats_table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.stats_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stats_table.setProperty(u"showDropIndicator", False)
        self.stats_table.setDragDropOverwriteMode(False)
        self.stats_table.setAlternatingRowColors(False)
        self.stats_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.stats_table.setSupportedDragActions(Qt.DropAction.IgnoreAction)
        self.stats_table.horizontalHeader().setVisible(False)
        self.stats_table.horizontalHeader().setCascadingSectionResizes(False)
        self.stats_table.verticalHeader().setVisible(True)
        self.stats_table.verticalHeader().setHighlightSections(True)

        self.horizontalLayout_4.addWidget(self.stats_table)

        self.splitter.addWidget(self.numbers_box)

        self.horizontalLayout_3.addWidget(self.splitter)

        self.stacked_content.addWidget(self.stats_page)
        self.error_page = QWidget()
        self.error_page.setObjectName(u"error_page")
        self.verticalLayout_6 = QVBoxLayout(self.error_page)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.error_label = QLabel(self.error_page)
        self.error_label.setObjectName(u"error_label")
        font2 = QFont()
        font2.setPointSize(20)
        self.error_label.setFont(font2)
        self.error_label.setStyleSheet(u"QLabel {\n"
"	color: rgb(255, 0, 0);\n"
"}")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout_6.addWidget(self.error_label)

        self.error_content = QPlainTextEdit(self.error_page)
        self.error_content.setObjectName(u"error_content")
        self.error_content.setFrameShape(QFrame.Shape.NoFrame)
        self.error_content.setFrameShadow(QFrame.Shadow.Plain)
        self.error_content.setUndoRedoEnabled(False)
        self.error_content.setReadOnly(True)

        self.verticalLayout_6.addWidget(self.error_content)

        self.stacked_content.addWidget(self.error_page)
        self.init_page = QWidget()
        self.init_page.setObjectName(u"init_page")
        self.verticalLayout_7 = QVBoxLayout(self.init_page)
        self.verticalLayout_7.setObjectName(u"verticalLayout_7")
        self.label_3 = QLabel(self.init_page)
        self.label_3.setObjectName(u"label_3")
        sizePolicy4.setHeightForWidth(self.label_3.sizePolicy().hasHeightForWidth())
        self.label_3.setSizePolicy(sizePolicy4)
        self.label_3.setFont(font2)
        self.label_3.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout_7.addWidget(self.label_3)

        self.stacked_content.addWidget(self.init_page)

        self.verticalLayout_2.addWidget(self.stacked_content)


        self.retranslateUi(StatisticsWidget)
        self.custom_radio.toggled.connect(self.custom_period_box.setEnabled)
        self.stats_table.itemChanged.connect(self.stats_table.resizeColumnsToContents)
        self.custom_start_check.toggled.connect(self.custom_start.setDisabled)
        self.custom_end_check.toggled.connect(self.custom_end.setDisabled)

        self.stacked_content.setCurrentIndex(1)


        QMetaObject.connectSlotsByName(StatisticsWidget)
    # setupUi

    def retranslateUi(self, StatisticsWidget):
        StatisticsWidget.setWindowTitle(QCoreApplication.translate("StatisticsWidget", u"Form", None))
        self.range_box.setTitle(QCoreApplication.translate("StatisticsWidget", u"Period", None))
        self.custom_start_label.setText(QCoreApplication.translate("StatisticsWidget", u"Start:", None))
        self.custom_start.setDisplayFormat(QCoreApplication.translate("StatisticsWidget", u"M/d/yyyy h:mm\u202fAp", None))
        self.custom_start_check.setText(QCoreApplication.translate("StatisticsWidget", u"Beginning of time", None))
        self.custom_end_label.setText(QCoreApplication.translate("StatisticsWidget", u"End:", None))
        self.custom_end.setDisplayFormat(QCoreApplication.translate("StatisticsWidget", u"M/d/yyyy h:mm\u202fAp", None))
        self.custom_end_check.setText(QCoreApplication.translate("StatisticsWidget", u"End of time", None))
        self.data_points_label.setText(QCoreApplication.translate("StatisticsWidget", u"Data Points:", None))
        self.month_radio.setText(QCoreApplication.translate("StatisticsWidget", u"Month", None))
        self.year_radio.setText(QCoreApplication.translate("StatisticsWidget", u"Year", None))
        self.generate_button.setText(QCoreApplication.translate("StatisticsWidget", u"Generate", None))
        self.all_time_radio.setText(QCoreApplication.translate("StatisticsWidget", u"All Time", None))
        self.yesterday_radio.setText(QCoreApplication.translate("StatisticsWidget", u"Yesterday", None))
        self.today_radio.setText(QCoreApplication.translate("StatisticsWidget", u"Today", None))
        self.custom_radio.setText(QCoreApplication.translate("StatisticsWidget", u"Custom", None))
        self.week_radio.setText(QCoreApplication.translate("StatisticsWidget", u"Week", None))
        self.label.setText(QCoreApplication.translate("StatisticsWidget", u"Loading statistics...", None))
        self.label_2.setText(QCoreApplication.translate("StatisticsWidget", u"Please wait...", None))
        self.cancel_button.setText(QCoreApplication.translate("StatisticsWidget", u"Cancel", None))
        self.graph_box.setTitle(QCoreApplication.translate("StatisticsWidget", u"Graph", None))
        self.snapshots_graph_radio.setText(QCoreApplication.translate("StatisticsWidget", u"Snapshots", None))
        self.files_graph_radio.setText(QCoreApplication.translate("StatisticsWidget", u"Files", None))
        self.size_graph_radio.setText(QCoreApplication.translate("StatisticsWidget", u"Size", None))
        self.urls_graph_radio.setText(QCoreApplication.translate("StatisticsWidget", u"URLs", None))
        self.hosts_graph_radio.setText(QCoreApplication.translate("StatisticsWidget", u"Hosts", None))
        self.dx_label_label.setText(QCoreApplication.translate("StatisticsWidget", u"\u2206x = ", None))
        self.dx_label.setText(QCoreApplication.translate("StatisticsWidget", u"1d", None))
        self.numbers_box.setTitle(QCoreApplication.translate("StatisticsWidget", u"Statistics", None))
        ___qtablewidgetitem = self.stats_table.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("StatisticsWidget", u"property", None))
        ___qtablewidgetitem1 = self.stats_table.verticalHeaderItem(0)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("StatisticsWidget", u"Period", None))
        ___qtablewidgetitem2 = self.stats_table.verticalHeaderItem(1)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("StatisticsWidget", u"Snapshots", None))
        ___qtablewidgetitem3 = self.stats_table.verticalHeaderItem(2)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("StatisticsWidget", u"Files", None))
        ___qtablewidgetitem4 = self.stats_table.verticalHeaderItem(3)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("StatisticsWidget", u"Size", None))
        ___qtablewidgetitem5 = self.stats_table.verticalHeaderItem(4)
        ___qtablewidgetitem5.setText(QCoreApplication.translate("StatisticsWidget", u"URLs", None))
        ___qtablewidgetitem6 = self.stats_table.verticalHeaderItem(5)
        ___qtablewidgetitem6.setText(QCoreApplication.translate("StatisticsWidget", u"Hosts", None))

        __sortingEnabled = self.stats_table.isSortingEnabled()
        self.stats_table.setSortingEnabled(False)
        ___qtablewidgetitem7 = self.stats_table.item(0, 0)
        ___qtablewidgetitem7.setText(QCoreApplication.translate("StatisticsWidget", u"Oct 26 2026 12:00 AM - Oct 26 2026 11:59 PM (23h59m)", None))
        ___qtablewidgetitem8 = self.stats_table.item(1, 0)
        ___qtablewidgetitem8.setText(QCoreApplication.translate("StatisticsWidget", u"1", None))
        ___qtablewidgetitem9 = self.stats_table.item(2, 0)
        ___qtablewidgetitem9.setText(QCoreApplication.translate("StatisticsWidget", u"12", None))
        ___qtablewidgetitem10 = self.stats_table.item(3, 0)
        ___qtablewidgetitem10.setText(QCoreApplication.translate("StatisticsWidget", u"12KiB", None))
        ___qtablewidgetitem11 = self.stats_table.item(4, 0)
        ___qtablewidgetitem11.setText(QCoreApplication.translate("StatisticsWidget", u"1", None))
        ___qtablewidgetitem12 = self.stats_table.item(5, 0)
        ___qtablewidgetitem12.setText(QCoreApplication.translate("StatisticsWidget", u"1", None))
        self.stats_table.setSortingEnabled(__sortingEnabled)

        self.error_label.setText(QCoreApplication.translate("StatisticsWidget", u"An Error Occured while generating the statistical report!", None))
        self.label_3.setText(QCoreApplication.translate("StatisticsWidget", u"Please use the \"Generate\" button above to run a statistics querry.", None))
    # retranslateUi

