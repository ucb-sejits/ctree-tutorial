#ifndef PRIORITY_QUEUE_H
#define PRIORITY_QUEUE_H

typedef double HeapElement;

struct PriorityQueue {
	HeapElement* array;
	unsigned size;
	unsigned max_size;
};

struct PriorityQueue* new_priority_queue(unsigned const heap_size);

int priority_queue_push(struct PriorityQueue* const heap,
                        const HeapElement element);

HeapElement* find_priority_queue_min(const struct PriorityQueue* heap);

int delete_priority_queue_min(struct PriorityQueue* const heap);

HeapElement priority_queue_pop(struct PriorityQueue* const heap);

void free_priority_queue(struct PriorityQueue* const heap);

#endif
