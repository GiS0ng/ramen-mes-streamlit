PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS item (
 item_id INTEGER PRIMARY KEY, item_code TEXT NOT NULL UNIQUE, item_name TEXT NOT NULL,
 item_type TEXT NOT NULL CHECK(item_type IN ('PRODUCT','MATERIAL')), unit TEXT NOT NULL,
 safety_stock REAL NOT NULL DEFAULT 0 CHECK(safety_stock>=0),
 is_active TEXT NOT NULL DEFAULT 'Y' CHECK(is_active IN ('Y','N'))
);
CREATE TABLE IF NOT EXISTS business_partner (
 partner_id INTEGER PRIMARY KEY, partner_code TEXT NOT NULL UNIQUE, partner_name TEXT NOT NULL,
 partner_type TEXT NOT NULL CHECK(partner_type IN ('SUPPLIER','CUSTOMER','BOTH')),
 business_number TEXT, representative_name TEXT, phone TEXT, email TEXT, address TEXT,
 is_active TEXT NOT NULL DEFAULT 'Y' CHECK(is_active IN ('Y','N'))
);
CREATE TABLE IF NOT EXISTS equipment (
 equipment_id INTEGER PRIMARY KEY, equipment_code TEXT NOT NULL UNIQUE, equipment_name TEXT NOT NULL,
 equipment_type TEXT, location TEXT,
 capacity_per_minute REAL NOT NULL DEFAULT 1 CHECK(capacity_per_minute>0),
 status TEXT NOT NULL DEFAULT 'AVAILABLE'
 CHECK(status IN ('AVAILABLE','RUNNING','STOPPED','MAINTENANCE')),
 is_active TEXT NOT NULL DEFAULT 'Y' CHECK(is_active IN ('Y','N'))
);
CREATE TABLE IF NOT EXISTS lot (
 lot_id INTEGER PRIMARY KEY, lot_no TEXT NOT NULL UNIQUE, item_id INTEGER NOT NULL REFERENCES item(item_id),
 lot_type TEXT NOT NULL CHECK(lot_type IN ('RECEIPT','PRODUCTION')),
 initial_qty REAL NOT NULL CHECK(initial_qty>=0), qty REAL NOT NULL CHECK(qty>=0 AND qty<=initial_qty),
 received_date TEXT, produced_date TEXT, expire_date TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS production (
 production_id INTEGER PRIMARY KEY, production_no TEXT NOT NULL UNIQUE,
 item_id INTEGER NOT NULL REFERENCES item(item_id), output_lot_id INTEGER NOT NULL UNIQUE REFERENCES lot(lot_id),
 equipment_id INTEGER REFERENCES equipment(equipment_id), production_date TEXT NOT NULL,
 input_qty REAL NOT NULL DEFAULT 0 CHECK(input_qty>=0), qty REAL NOT NULL CHECK(qty>0),
 planned_start_time TEXT, planned_end_time TEXT, actual_start_time TEXT, actual_end_time TEXT,
 status TEXT NOT NULL DEFAULT 'PLANNED' CHECK(status IN ('PLANNED','IN_PROGRESS','COMPLETED','CANCELED')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS production_material (
 production_material_id INTEGER PRIMARY KEY, production_id INTEGER NOT NULL REFERENCES production(production_id) ON DELETE CASCADE,
 material_lot_id INTEGER NOT NULL REFERENCES lot(lot_id), qty REAL NOT NULL CHECK(qty>0),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(production_id,material_lot_id)
);
CREATE TABLE IF NOT EXISTS purchase_order (
 purchase_order_id INTEGER PRIMARY KEY, purchase_order_no TEXT NOT NULL UNIQUE,
 supplier_id INTEGER NOT NULL REFERENCES business_partner(partner_id), order_date TEXT NOT NULL,
 expected_date TEXT, status TEXT NOT NULL DEFAULT 'ORDERED' CHECK(status IN ('ORDERED','PARTIAL_RECEIVED','RECEIVED','CANCELED')),
 memo TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS purchase_order_detail (
 purchase_order_detail_id INTEGER PRIMARY KEY, purchase_order_id INTEGER NOT NULL REFERENCES purchase_order(purchase_order_id) ON DELETE CASCADE,
 material_item_id INTEGER NOT NULL REFERENCES item(item_id), order_qty REAL NOT NULL CHECK(order_qty>0),
 received_qty REAL NOT NULL DEFAULT 0 CHECK(received_qty>=0 AND received_qty<=order_qty), unit_price REAL NOT NULL DEFAULT 0 CHECK(unit_price>=0),
 UNIQUE(purchase_order_id,material_item_id)
);
CREATE TABLE IF NOT EXISTS material_receipt (
 material_receipt_id INTEGER PRIMARY KEY, receipt_no TEXT NOT NULL UNIQUE,
 purchase_order_detail_id INTEGER REFERENCES purchase_order_detail(purchase_order_detail_id),
 material_lot_id INTEGER NOT NULL UNIQUE REFERENCES lot(lot_id), receipt_date TEXT NOT NULL,
 receipt_qty REAL NOT NULL CHECK(receipt_qty>0), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shipment_schedule (
 shipment_schedule_id INTEGER PRIMARY KEY, shipment_schedule_no TEXT NOT NULL UNIQUE,
 customer_id INTEGER NOT NULL REFERENCES business_partner(partner_id), item_id INTEGER NOT NULL REFERENCES item(item_id),
 scheduled_date TEXT NOT NULL, scheduled_qty REAL NOT NULL CHECK(scheduled_qty>0),
 shipped_qty REAL NOT NULL DEFAULT 0 CHECK(shipped_qty>=0 AND shipped_qty<=scheduled_qty),
 status TEXT NOT NULL DEFAULT 'PLANNED' CHECK(status IN ('PLANNED','PARTIAL_SHIPPED','SHIPPED','CANCELED')),
 memo TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shipment (
 shipment_id INTEGER PRIMARY KEY, shipment_no TEXT NOT NULL UNIQUE,
 shipment_schedule_id INTEGER REFERENCES shipment_schedule(shipment_schedule_id),
 customer_id INTEGER NOT NULL REFERENCES business_partner(partner_id), shipment_date TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'READY' CHECK(status IN ('READY','SHIPPED','CANCELED','RETURNED')),
 memo TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shipment_detail (
 shipment_detail_id INTEGER PRIMARY KEY, shipment_id INTEGER NOT NULL REFERENCES shipment(shipment_id) ON DELETE CASCADE,
 product_lot_id INTEGER NOT NULL REFERENCES lot(lot_id), shipment_qty REAL NOT NULL CHECK(shipment_qty>0),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(shipment_id,product_lot_id)
);
CREATE TABLE IF NOT EXISTS product_box (
 product_box_id INTEGER PRIMARY KEY, box_no TEXT NOT NULL UNIQUE,
 product_lot_id INTEGER NOT NULL REFERENCES lot(lot_id),
 box_qty INTEGER NOT NULL DEFAULT 40 CHECK(box_qty=40),
 packed_date TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS production_request (
 production_request_id INTEGER PRIMARY KEY, request_no TEXT NOT NULL UNIQUE,
 item_id INTEGER NOT NULL REFERENCES item(item_id), equipment_id INTEGER REFERENCES equipment(equipment_id),
 requested_qty INTEGER NOT NULL CHECK(requested_qty>0),
 request_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'COMPLETED'
 CHECK(status IN ('PLANNED','IN_PROGRESS','COMPLETED','CANCELED')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS production_request_unit (
 production_request_unit_id INTEGER PRIMARY KEY,
 production_request_id INTEGER NOT NULL REFERENCES production_request(production_request_id) ON DELETE CASCADE,
 production_id INTEGER NOT NULL UNIQUE REFERENCES production(production_id) ON DELETE CASCADE,
 UNIQUE(production_request_id,production_id)
);
CREATE TABLE IF NOT EXISTS packing_box (
 packing_box_id INTEGER PRIMARY KEY, box_no TEXT NOT NULL UNIQUE,
 box_qty INTEGER NOT NULL DEFAULT 40 CHECK(box_qty=40), packed_date TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS packing_box_detail (
 packing_box_detail_id INTEGER PRIMARY KEY,
 packing_box_id INTEGER NOT NULL REFERENCES packing_box(packing_box_id) ON DELETE CASCADE,
 product_lot_id INTEGER NOT NULL UNIQUE REFERENCES lot(lot_id),
 UNIQUE(packing_box_id,product_lot_id)
);
CREATE TABLE IF NOT EXISTS defect_code (
 defect_code_id INTEGER PRIMARY KEY, defect_code TEXT NOT NULL UNIQUE, defect_name TEXT NOT NULL,
 description TEXT, is_active TEXT NOT NULL DEFAULT 'Y' CHECK(is_active IN ('Y','N'))
);
CREATE TABLE IF NOT EXISTS production_defect (
 production_defect_id INTEGER PRIMARY KEY, production_id INTEGER NOT NULL REFERENCES production(production_id) ON DELETE CASCADE,
 defect_code_id INTEGER NOT NULL REFERENCES defect_code(defect_code_id), defect_qty REAL NOT NULL CHECK(defect_qty>0),
 defect_date TEXT NOT NULL, memo TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(production_id,defect_code_id)
);
CREATE TABLE IF NOT EXISTS equipment_operation (
 equipment_operation_id INTEGER PRIMARY KEY, equipment_id INTEGER NOT NULL REFERENCES equipment(equipment_id),
 production_id INTEGER REFERENCES production(production_id), operation_date TEXT NOT NULL,
 planned_minutes INTEGER NOT NULL DEFAULT 0 CHECK(planned_minutes>=0),
 running_minutes INTEGER NOT NULL DEFAULT 0 CHECK(running_minutes>=0 AND running_minutes<=planned_minutes),
 downtime_minutes INTEGER NOT NULL DEFAULT 0 CHECK(downtime_minutes>=0 AND running_minutes+downtime_minutes<=planned_minutes),
 downtime_reason TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(equipment_id,operation_date,production_id)
);

CREATE INDEX IF NOT EXISTS idx_lot_item_id ON lot(item_id);
CREATE INDEX IF NOT EXISTS idx_lot_type ON lot(lot_type);
CREATE INDEX IF NOT EXISTS idx_lot_expire_date ON lot(expire_date);
CREATE INDEX IF NOT EXISTS idx_production_item_id ON production(item_id);
CREATE INDEX IF NOT EXISTS idx_production_equipment_id ON production(equipment_id);
CREATE INDEX IF NOT EXISTS idx_production_date ON production(production_date);
CREATE INDEX IF NOT EXISTS idx_production_material_production_id ON production_material(production_id);
CREATE INDEX IF NOT EXISTS idx_production_material_lot_id ON production_material(material_lot_id);
CREATE INDEX IF NOT EXISTS idx_purchase_order_supplier_id ON purchase_order(supplier_id);
CREATE INDEX IF NOT EXISTS idx_purchase_order_date ON purchase_order(order_date);
CREATE INDEX IF NOT EXISTS idx_shipment_schedule_customer_id ON shipment_schedule(customer_id);
CREATE INDEX IF NOT EXISTS idx_shipment_schedule_date ON shipment_schedule(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_shipment_customer_id ON shipment(customer_id);
CREATE INDEX IF NOT EXISTS idx_shipment_date ON shipment(shipment_date);
CREATE INDEX IF NOT EXISTS idx_shipment_detail_lot_id ON shipment_detail(product_lot_id);
CREATE INDEX IF NOT EXISTS idx_product_box_lot_id ON product_box(product_lot_id);
CREATE INDEX IF NOT EXISTS idx_packing_box_detail_box ON packing_box_detail(packing_box_id);
CREATE INDEX IF NOT EXISTS idx_production_defect_production_id ON production_defect(production_id);
CREATE INDEX IF NOT EXISTS idx_equipment_operation_equipment_id ON equipment_operation(equipment_id);

CREATE VIEW IF NOT EXISTS v_material_stock AS
SELECT i.item_code,i.item_name,l.lot_no,l.initial_qty,l.qty current_qty,i.safety_stock,
 CASE WHEN l.qty<=0 THEN '소진' WHEN l.qty<i.safety_stock THEN '안전재고 미만' ELSE '정상' END stock_status,
 l.received_date,l.expire_date,i.unit
FROM lot l JOIN item i ON i.item_id=l.item_id WHERE l.lot_type='RECEIPT';

CREATE VIEW IF NOT EXISTS v_equipment_performance AS
SELECT p.production_id,p.production_no,e.equipment_name,p.qty production_qty,p.input_qty,
 COALESCE(SUM(pd.defect_qty),0) defect_qty,
 ROUND((p.qty-COALESCE(SUM(pd.defect_qty),0))*100.0/NULLIF(p.qty,0),2) yield_rate,
 ROUND(p.qty*100.0/NULLIF(p.input_qty,0),2) input_performance
FROM production p LEFT JOIN equipment e ON e.equipment_id=p.equipment_id
LEFT JOIN production_defect pd ON pd.production_id=p.production_id GROUP BY p.production_id;

CREATE VIEW IF NOT EXISTS v_shipment_production_trace AS
SELECT bp.partner_id,bp.partner_name customer_name,s.shipment_no,s.shipment_date,p.production_no,
 l.lot_no product_lot_no,sd.shipment_qty,i.item_name,i.unit
FROM shipment s JOIN business_partner bp ON bp.partner_id=s.customer_id
JOIN shipment_detail sd ON sd.shipment_id=s.shipment_id JOIN lot l ON l.lot_id=sd.product_lot_id
JOIN production p ON p.output_lot_id=l.lot_id JOIN item i ON i.item_id=p.item_id;

CREATE TRIGGER IF NOT EXISTS trg_production_material_before_insert BEFORE INSERT ON production_material BEGIN
 SELECT CASE WHEN (SELECT lot_type FROM lot WHERE lot_id=NEW.material_lot_id)<>'RECEIPT' THEN RAISE(ABORT,'원재료 입고 LOT만 투입할 수 있습니다.') END;
 SELECT CASE WHEN (SELECT qty FROM lot WHERE lot_id=NEW.material_lot_id)<NEW.qty THEN RAISE(ABORT,'원재료 LOT 재고가 부족합니다.') END;
END;
CREATE TRIGGER IF NOT EXISTS trg_production_material_after_insert AFTER INSERT ON production_material BEGIN
 UPDATE lot SET qty=qty-NEW.qty WHERE lot_id=NEW.material_lot_id;
 UPDATE production SET input_qty=(SELECT COALESCE(SUM(qty),0) FROM production_material WHERE production_id=NEW.production_id) WHERE production_id=NEW.production_id;
END;
CREATE TRIGGER IF NOT EXISTS trg_production_material_before_update BEFORE UPDATE ON production_material BEGIN
 SELECT CASE WHEN (SELECT qty FROM lot WHERE lot_id=NEW.material_lot_id)+(CASE WHEN OLD.material_lot_id=NEW.material_lot_id THEN OLD.qty ELSE 0 END)<NEW.qty THEN RAISE(ABORT,'변경할 원재료 LOT 재고가 부족합니다.') END;
END;
CREATE TRIGGER IF NOT EXISTS trg_production_material_after_update AFTER UPDATE ON production_material BEGIN
 UPDATE lot SET qty=qty+OLD.qty WHERE lot_id=OLD.material_lot_id;
 UPDATE lot SET qty=qty-NEW.qty WHERE lot_id=NEW.material_lot_id;
 UPDATE production SET input_qty=(SELECT COALESCE(SUM(qty),0) FROM production_material WHERE production_id=NEW.production_id) WHERE production_id IN (OLD.production_id,NEW.production_id);
END;
CREATE TRIGGER IF NOT EXISTS trg_production_material_after_delete AFTER DELETE ON production_material BEGIN
 UPDATE lot SET qty=qty+OLD.qty WHERE lot_id=OLD.material_lot_id;
 UPDATE production SET input_qty=(SELECT COALESCE(SUM(qty),0) FROM production_material WHERE production_id=OLD.production_id) WHERE production_id=OLD.production_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_shipment_detail_before_insert BEFORE INSERT ON shipment_detail BEGIN
 SELECT CASE WHEN (SELECT lot_type FROM lot WHERE lot_id=NEW.product_lot_id)<>'PRODUCTION' THEN RAISE(ABORT,'완제품 생산 LOT만 출하할 수 있습니다.') END;
 SELECT CASE WHEN (SELECT qty FROM lot WHERE lot_id=NEW.product_lot_id)<NEW.shipment_qty THEN RAISE(ABORT,'완제품 LOT 재고가 부족합니다.') END;
 SELECT CASE WHEN (SELECT shipment_schedule_id FROM shipment WHERE shipment_id=NEW.shipment_id) IS NOT NULL AND
   (SELECT shipped_qty+NEW.shipment_qty>scheduled_qty FROM shipment_schedule WHERE shipment_schedule_id=(SELECT shipment_schedule_id FROM shipment WHERE shipment_id=NEW.shipment_id))
   THEN RAISE(ABORT,'출하계획 수량을 초과합니다.') END;
END;
CREATE TRIGGER IF NOT EXISTS trg_shipment_detail_after_insert AFTER INSERT ON shipment_detail BEGIN
 UPDATE lot SET qty=qty-NEW.shipment_qty WHERE lot_id=NEW.product_lot_id;
 UPDATE shipment_schedule SET shipped_qty=shipped_qty+NEW.shipment_qty,
 status=CASE WHEN shipped_qty+NEW.shipment_qty>=scheduled_qty THEN 'SHIPPED' ELSE 'PARTIAL_SHIPPED' END
 WHERE shipment_schedule_id=(SELECT shipment_schedule_id FROM shipment WHERE shipment_id=NEW.shipment_id);
END;
CREATE TRIGGER IF NOT EXISTS trg_shipment_detail_before_update BEFORE UPDATE ON shipment_detail BEGIN
 SELECT CASE WHEN (SELECT qty FROM lot WHERE lot_id=NEW.product_lot_id)+(CASE WHEN OLD.product_lot_id=NEW.product_lot_id THEN OLD.shipment_qty ELSE 0 END)<NEW.shipment_qty THEN RAISE(ABORT,'변경할 완제품 LOT 재고가 부족합니다.') END;
END;
CREATE TRIGGER IF NOT EXISTS trg_shipment_detail_after_update AFTER UPDATE ON shipment_detail BEGIN
 UPDATE lot SET qty=qty+OLD.shipment_qty WHERE lot_id=OLD.product_lot_id;
 UPDATE lot SET qty=qty-NEW.shipment_qty WHERE lot_id=NEW.product_lot_id;
 UPDATE shipment_schedule SET shipped_qty=(SELECT COALESCE(SUM(sd.shipment_qty),0) FROM shipment_detail sd JOIN shipment sh ON sh.shipment_id=sd.shipment_id WHERE sh.shipment_schedule_id=shipment_schedule.shipment_schedule_id),
 status=CASE WHEN (SELECT COALESCE(SUM(sd.shipment_qty),0) FROM shipment_detail sd JOIN shipment sh ON sh.shipment_id=sd.shipment_id WHERE sh.shipment_schedule_id=shipment_schedule.shipment_schedule_id)>=scheduled_qty THEN 'SHIPPED' ELSE 'PARTIAL_SHIPPED' END
 WHERE shipment_schedule_id IN ((SELECT shipment_schedule_id FROM shipment WHERE shipment_id=OLD.shipment_id),(SELECT shipment_schedule_id FROM shipment WHERE shipment_id=NEW.shipment_id));
END;
CREATE TRIGGER IF NOT EXISTS trg_shipment_detail_after_delete AFTER DELETE ON shipment_detail BEGIN
 UPDATE lot SET qty=qty+OLD.shipment_qty WHERE lot_id=OLD.product_lot_id;
 UPDATE shipment_schedule SET shipped_qty=MAX(0,shipped_qty-OLD.shipment_qty),
 status=CASE WHEN shipped_qty-OLD.shipment_qty<=0 THEN 'PLANNED' ELSE 'PARTIAL_SHIPPED' END
 WHERE shipment_schedule_id=(SELECT shipment_schedule_id FROM shipment WHERE shipment_id=OLD.shipment_id);
END;
