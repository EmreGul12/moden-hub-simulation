from sequence.kernel.timeline import Timeline
from sequence.topology.node import Node
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from sequence.components.memory import MemoryArray
from sequence.components.light_source import LightSource
import random
from sequence.kernel.event import Event
from sequence.kernel.process import Process
import math


metrics = {
    "total_app_requests": 0,
    "cache_hits": 0,
    "hub_routed_requests": 0,
    "success_within_R3": 0,
    "dropped_R3": 0,
    "total_photons_fired": 0
}

def build_moden_hub_topology():
    tl = Timeline(1e12)

    # Fiziksel Düğümlerin (Nodes) Oluşturulması
    hub = Node("Hub", tl)
    qpus = []
    
    # Etraftaki 4 adet QPU düğümünü oluşturuyoruz
    for i in range(4):
        qpu = Node(f"QPU_{i}", tl)
        qpus.append(qpu)

    
    distance_km = 10.0  # Düğümler arası mesafe (10 km)
    attenuation = 0.2   # Fiber zayıflaması (0.2 dB/km - Endüstri standardı)

    for qpu in qpus:
        # A) Kuantum Veri Kanalı (Sadece Hub'dan QPU'ya foton aktarımı için)
        qc = QuantumChannel(f"qc_hub_to_{qpu.name}", tl, distance=distance_km, attenuation=attenuation)
        qc.set_ends(hub, qpu.name)

        # B) Klasik Kontrol Kanalları (İstekler ve API mesajları için Çift Yönlü)
        cc_to_qpu = ClassicalChannel(f"cc_hub_to_{qpu.name}", tl, distance=distance_km)
        cc_to_qpu.set_ends(hub, qpu.name)

        cc_from_qpu = ClassicalChannel(f"cc_{qpu.name}_to_hub", tl, distance=distance_km)
        cc_from_qpu.set_ends(qpu, hub.name)

    print("Parça 1 Tamamlandı: Yıldız Topolojisi ve Fiber Kanallar başarıyla kuruldu!")
    return tl, hub, qpus

def assign_hardware(tl, hub, qpus):
    # 1. Kuantum Bellek Kapasitesi ve Bozulma Süresi (Decoherence)
    memory_capacity = 5   # Makaledeki gibi her QPU için 5 yuvalı bellek
    coherence_time = 1e9  # 1 milisaniye (SeQUeNCe pikosaniye çalıştığı için 1e9 ps)

    for qpu in qpus:
        # QPU için bellek dizisini oluşturuyoruz
        mem_array = MemoryArray(f"MemArray_{qpu.name}", tl, num_memories=memory_capacity)
        
        # Bellekteki her bir yuvanın (memory) bozulma ömrünü fiziksel olarak atıyoruz
        for mem in mem_array.memories:
            mem.coherence_time = coherence_time
            
        # Bellek donanımını QPU cihazının içine ekliyoruz
        qpu.add_component(mem_array)
        qpu.memory_array = mem_array

    # 2. Merkez Hub'a Işık/Foton Kaynağı Eklenmesi
    hub_source = LightSource("Hub_Photon_Source", tl, frequency=8e7) # 80 MHz üretim hızı
    
    # Foton kaynağını Hub cihazına ekliyoruz
    hub.add_component(hub_source)
    hub.photon_source = hub_source

    print(" Kuantum bellekler ve foton kaynağı donanımlara yerleştirildi!")
    return hub, qpus

def hub_receive_request(tl, sender, receiver, total_qpus):
    print(f"   -> Merkez Hub: {sender.name} ve {receiver.name} için istek aldı.")
    
    k_shots = max(1, int(2 * math.log2(total_qpus) + 1))
    distance_km = 10.0
    attenuation = 0.2 
    transmittance = 10 ** (-(distance_km * attenuation) / 10)
    p_pair_success = transmittance * transmittance

    R_max = 3 
    success = False

    for round_num in range(1, R_max + 1):
        print(f"      [Tur {round_num}/{R_max}] Hub {k_shots} adet paralel foton ateşliyor...")
        metrics["total_photons_fired"] += k_shots # Maliyeti kaydet
        
        successful_pairs = 0
        for _ in range(k_shots):
            if random.random() < p_pair_success:
                successful_pairs += 1

        if successful_pairs > 0:
            print(f"      [BAŞARILI] {successful_pairs} adet Bell çifti fiber kayıplarını aşıp uçlara ulaştı!")
            success = True
            metrics["success_within_R3"] += 1 # Başarı sayacını artır
            
            if successful_pairs > 1:
                sender.cache[receiver.name] = tl.now()
                receiver.cache[sender.name] = tl.now()
                print(f"      [CACHE EKLENDİ] Artan 1 Bell çifti yedeklendi.")
            break # Başarılı olduysa diğer turları atla 
        else:
            print(f"      [BAŞARISIZ] Fotonlar sönümlendi. Yeni tura geçiliyor...")

    # 3 Tur bittiğinde hala başarı yoksa:
    if not success:
        print(f"      [İPTAL - R=3] 3 tur boyunca başarı sağlanamadı. İstek ZAMAN AŞIMINA uğradı.")
        metrics["dropped_requests_R3"] = metrics.get("dropped_R3", 0) + 1 # İptal sayacını artır
        
    print("-" * 60)



class TrafficGenerator:
    def __init__(self, tl, qpus, request_rate):
        self.tl = tl
        self.qpus = qpus
        self.request_rate = request_rate
        for qpu in self.qpus:
            qpu.cache = {}

    def start(self):
        self.schedule_next()

    def schedule_next(self):
        next_time = self.tl.now() + int(random.expovariate(1.0 / self.request_rate))
        if next_time < self.tl.stop_time:
            process = Process(self, "generate_request", [])
            event = Event(next_time, process)
            self.tl.schedule(event)

    def generate_request(self):
        sender = random.choice(self.qpus)
        receiver = random.choice([q for q in self.qpus if q != sender])
        time_sec = self.tl.now() / 1e12
        print(f"\n[{time_sec:.4f} sn] UYGULAMA KATMANI: {sender.name}, {receiver.name} ile iletişim kurmak istiyor.")
        
        metrics["total_app_requests"] += 1 # Toplam istek sayacını artır

        coherence_time = 1e9 
        if receiver.name in sender.cache:
            cache_time = sender.cache[receiver.name]
            time_passed = self.tl.now() - cache_time
            
            if time_passed <= coherence_time:
                print(f"   -> [CACHE HIT] Mükemmel! {sender.name} belleğinde bozulmamış bir Bell çifti buldu.")
                metrics["cache_hits"] += 1 # Cache hit sayacını artır
                del sender.cache[receiver.name]
                del receiver.cache[sender.name]
                print("-" * 60)
                self.schedule_next()
                return  
            else:
                print(f"   -> [CACHE MISS] Bellekte çift vardı ama süresi dolduğu için çökmüş (Decoherence).")
                del sender.cache[receiver.name]
                del receiver.cache[sender.name]

        metrics["hub_routed_requests"] += 1 # Hub'a düşen istek sayacını artır
        hub_receive_request(self.tl, sender, receiver, len(self.qpus))
        self.schedule_next()

if __name__ == "__main__":
    
    tl, hub, qpus = build_moden_hub_topology()
    
    
    hub, qpus = assign_hardware(tl, hub, qpus)
    
    
    # Saniyede ortalama 5 istek üretecek şekilde ayarlıyoruz (1e12 / 5)
    traffic_app = TrafficGenerator(tl, qpus, request_rate=(1e12 / 5))
    traffic_app.start()
    
    print("Parça 3 Tamamlandı: Ağ trafiği jeneratörü başlatıldı!\n")
    print("--- SİMÜLASYON BAŞLIYOR ---")
    
    # Simülasyonu çalıştır.Bütün zamanlanmış olayları tetikleme
    tl.init()
    tl.run()
    tl.run()

    # SONUÇ RAPORU
    print("\n" + "="*50)
    print(" 📊 MODEN-HUB BASELINE SİMÜLASYON RAPORU")
    print("="*50)
    print(f"Uygulama Katmanı Toplam İstek: {metrics['total_app_requests']}")
    print(f"Önbellekten Karşılanan (Cache Hit): {metrics['cache_hits']}")
    print(f"Merkeze (Hub) Giden İstek: {metrics['hub_routed_requests']}")
    print(f"R=3 Tur İçinde Başarılı: {metrics['success_within_R3']}")
    print(f"Zaman Aşımı (İptal/Drop): {metrics.get('dropped_R3', 0) + metrics.get('dropped_requests_R3', 0)}")
    print(f"Kullanılan Toplam Foton (Maliyet): {metrics['total_photons_fired']}")
    print("="*50)