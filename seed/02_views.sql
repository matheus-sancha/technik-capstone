-- The two views the agent reads wherever a rule lives. Run as SYSADMIN, after the tables are loaded.
USE SCHEMA TECHNIK_DW.OPS;

CREATE OR REPLACE VIEW V_WORK_ORDER_OPERATIONS (
    WORK_ORDER        COMMENT 'SAP work order number, for example 100004521',
    OPERATION_SEQ     COMMENT 'Position of the operation in the work order routing',
    OPERATION         COMMENT 'Machining, Cladding, Welding, Bending, Coating or Assembly & Testing',
    WORK_CENTRE,
    PLANT,
    PROJECT,
    PART_NUMBER,
    OPERATION_STATUS  COMMENT 'Not started, In progress or Confirmed',
    WORK_ORDER_STATUS COMMENT 'Released, Partly confirmed, Confirmed or Technically complete',
    ROUTING_HOURS     COMMENT 'Planned hours for the operation',
    ACTUAL_HOURS      COMMENT 'Hours posted on the confirmation that counts',
    CONFIRMED_AT
)
COMMENT = 'One row per work order operation; superseded partial confirmations removed.
Efficiency % = SUM(ROUTING_HOURS) / SUM(ACTUAL_HOURS) * 100 over confirmed operations.'
AS
SELECT o.WO_NO, o.OP_SEQ, o.OPERATION, o.WORK_CENTER, w.PLANT, w.PROJECT_ID, w.PART_NO,
       CASE o.STATUS WHEN 'OPEN' THEN 'Not started' WHEN 'INPROC' THEN 'In progress'
                     WHEN 'CNF'  THEN 'Confirmed' END,
       CASE w.STATUS WHEN 'REL'  THEN 'Released'    WHEN 'PCNF'   THEN 'Partly confirmed'
                     WHEN 'CNF'  THEN 'Confirmed'   WHEN 'TECO'   THEN 'Technically complete' END,
       o.ROUTING_HOURS, o.ACTUAL_HOURS, o.CONFIRMED_AT
FROM SAP_WO_OPERATIONS o
JOIN SAP_WORK_ORDERS w ON w.WO_NO = o.WO_NO
WHERE w.STATUS <> 'CRTD'                      -- not released yet: nothing to report
QUALIFY ROW_NUMBER() OVER (PARTITION BY o.WO_NO, o.OP_SEQ
                           ORDER BY o.CONFIRMATION_NO DESC) = 1;

CREATE OR REPLACE VIEW V_RELEASED_REVISIONS
AS
WITH items AS (
    SELECT PART_NO    AS ITEM_NO, 'Part'        AS ITEM_TYPE, DESCRIPTION AS TITLE, REVISION, RELEASED_AT
      FROM TC_PARTS        WHERE RELEASE_STATUS = 'Released'
    UNION ALL
    SELECT DRAWING_NO,           'Drawing',                   TITLE,                REVISION, RELEASED_AT
      FROM TC_DRAWINGS     WHERE RELEASE_STATUS = 'Released'
    UNION ALL
    SELECT PROGRAM_NO,           'CNC Program', 'CNC program for ' || PART_NO || ' on ' || MACHINE, REVISION, RELEASED_AT
      FROM TC_CNC_PROGRAMS WHERE RELEASE_STATUS = 'Released'
    UNION ALL
    SELECT DOC_NO,               'Document',                  TITLE,                REVISION, RELEASED_AT
      FROM TC_DOCUMENTS    WHERE STATUS = 'Released'
)
SELECT i.ITEM_NO, i.ITEM_TYPE, i.TITLE, i.REVISION, i.RELEASED_AT,
       e.ECN_NO, e.TITLE AS ECN_TITLE
FROM items i
LEFT JOIN TC_ECN_AFFECTED_ITEMS a ON a.ITEM_NO = i.ITEM_NO AND a.TO_REV = i.REVISION
LEFT JOIN TC_ECNS e               ON e.ECN_NO = a.ECN_NO AND e.STATUS = 'Released';
